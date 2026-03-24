const crypto = require('node:crypto');
const { ImapFlow } = require('imapflow');
const { simpleParser } = require('mailparser');
const pdfParse = require('pdf-parse');
const db = require('../../infrastructure/db');
const { integrationService } = require('../../core/application');

function parseBoolean(value, fallback = false) {
  if (value === undefined || value === null || value === '') return fallback;
  return String(value).toLowerCase() === 'true';
}

function sha256(value) {
  return crypto.createHash('sha256').update(value).digest('hex');
}

function sanitizeError(error) {
  return String(error?.message || error || 'unknown').slice(0, 300);
}

function mailboxStateKey(config) {
  return `email_intake:last_uid:${config.emailIntake.imap.user}:${config.emailIntake.imap.folder}`;
}

async function parsePdfAttachment(attachment) {
  if (!attachment?.content) return { extractedText: '', parseError: 'NO_CONTENT' };
  try {
    const parsed = await pdfParse(attachment.content);
    return { extractedText: String(parsed?.text || '').slice(0, 20000), parseError: null };
  } catch (error) {
    return { extractedText: '', parseError: sanitizeError(error) };
  }
}

async function mapParsedEmail(message, parsed, config) {
  const attachments = [];
  let failedParseCount = 0;
  for (const attachment of parsed.attachments || []) {
    const base = {
      filename: attachment.filename || 'attachment',
      contentType: attachment.contentType || 'application/octet-stream',
      size: attachment.size || (attachment.content ? attachment.content.length : 0)
    };
    if (parseBoolean(config.emailIntake.allowAttachments, true)
      && parseBoolean(config.emailIntake.pdfParseEnabled, true)
      && String(base.contentType).toLowerCase().includes('pdf')) {
      const pdf = await parsePdfAttachment(attachment);
      if (pdf.parseError) failedParseCount += 1;
      attachments.push({ ...base, extractedText: pdf.extractedText, parseError: pdf.parseError });
    } else {
      attachments.push(base);
    }
  }

  const bodyText = String(parsed.text || parsed.html || '').slice(0, 50000);
  const normHash = sha256(`${parsed.subject || ''}\n${bodyText}\n${attachments.map((a) => `${a.filename}:${a.size}`).join('|')}`);

  return {
    source: 'imap',
    threadId: String(message.uid),
    messageId: parsed.messageId || null,
    from: parsed.from?.text || '',
    subject: parsed.subject || '',
    body: bodyText,
    date: parsed.date ? parsed.date.toISOString() : new Date().toISOString(),
    attachments,
    intakeMeta: {
      mailbox: config.emailIntake.imap.folder,
      uid: message.uid,
      flags: message.flags || [],
      normalizedHash: normHash,
      failedAttachmentParses: failedParseCount
    }
  };
}

function createEmailIntakePoller({ config, logger = console } = {}) {
  let timer = null;
  let running = false;
  let state = {
    enabled: false,
    lastPollAt: null,
    lastPollResult: 'not_started',
    lastError: null,
    processedCount: 0,
    duplicateCount: 0,
    failedParseCount: 0,
    lastEmailProcessed: null,
    connectionStatus: 'idle',
    folderStatus: 'unknown'
  };

  async function runOnce() {
    if (!config?.emailIntake?.enabled || !config?.emailIntake?.imap?.host) {
      state.enabled = false;
      state.lastPollResult = 'disabled';
      return state;
    }
    if (running) return state;

    running = true;
    state.enabled = true;
    state.lastPollAt = new Date().toISOString();
    const client = new ImapFlow({
      host: config.emailIntake.imap.host,
      port: config.emailIntake.imap.port,
      secure: config.emailIntake.imap.secure,
      auth: {
        user: config.emailIntake.imap.user,
        pass: config.emailIntake.imap.password
      },
      logger: false
    });

    try {
      await client.connect();
      state.connectionStatus = 'ok';
      await client.mailboxOpen(config.emailIntake.imap.folder);
      state.folderStatus = 'ok';

      const key = mailboxStateKey(config);
      const lastUid = Number(db.getMetaValue(key, 0) || 0);
      let maxUid = lastUid;
      let processedInPoll = 0;
      let duplicatesInPoll = 0;

      for await (const message of client.fetch({ uid: `${Math.max(1, lastUid + 1)}:*` }, { uid: true, source: true, flags: true })) {
        maxUid = Math.max(maxUid, Number(message.uid) || 0);
        const parsed = await simpleParser(message.source);
        const rawPayload = await mapParsedEmail(message, parsed, config);

        const event = await integrationService.receiveIntegrationEvent({
          sourceSystem: integrationService.INTEGRATION_SOURCES.EMAIL,
          eventType: integrationService.INTEGRATION_EVENT_TYPES.EMAIL_REQUEST_RECEIVED,
          rawPayload
        });

        if (event?.processingStatus === 'processed') processedInPoll += 1;
        else if (event?.processingStatus === 'received' || event?.processingStatus === 'normalized' || event?.processingStatus === 'processing') duplicatesInPoll += 1;

        state.lastEmailProcessed = {
          uid: message.uid,
          messageId: rawPayload.messageId || null,
          subject: rawPayload.subject || ''
        };
        state.failedParseCount += Number(rawPayload?.intakeMeta?.failedAttachmentParses || 0);
      }

      if (maxUid > lastUid) db.setMetaValue(key, maxUid);
      state.processedCount += processedInPoll;
      state.duplicateCount += duplicatesInPoll;
      state.lastPollResult = 'ok';
      state.lastError = null;
      logger.info('email intake poll completed', {
        mailbox: config.emailIntake.imap.folder,
        processedInPoll,
        duplicatesInPoll,
        lastUid,
        maxUid
      });
    } catch (error) {
      state.lastPollResult = 'failed';
      state.lastError = sanitizeError(error);
      state.connectionStatus = state.connectionStatus === 'ok' ? 'ok' : 'failed';
      state.folderStatus = state.folderStatus === 'ok' ? 'ok' : 'failed';
      logger.error('email intake poll failed', {
        mailbox: config.emailIntake?.imap?.folder || '',
        error: state.lastError,
        host: config.emailIntake?.imap?.host || '',
        userMasked: `${String(config.emailIntake?.imap?.user || '').slice(0, 2)}***`
      });
    } finally {
      running = false;
      await client.logout().catch(() => {});
    }

    db.setMetaValue('email_intake:diagnostics', state);
    return state;
  }

  function start() {
    if (timer) return;
    const intervalMs = Math.max(5000, Number(config?.emailIntake?.pollIntervalSeconds || 60) * 1000);
    timer = setInterval(() => {
      runOnce().catch((error) => {
        logger.error('email intake loop fatal error', { error: sanitizeError(error) });
      });
    }, intervalMs);
  }

  function stop() {
    if (!timer) return;
    clearInterval(timer);
    timer = null;
  }

  function getDiagnostics() {
    return { ...state, imapEnabled: Boolean(config?.emailIntake?.enabled), imapFolder: config?.emailIntake?.imap?.folder || '' };
  }

  return { start, stop, runOnce, getDiagnostics };
}

module.exports = { createEmailIntakePoller };
