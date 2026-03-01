class ExternalSourceAdapter:
    def import_contacts(self):
        raise NotImplementedError

    def import_requests(self):
        raise NotImplementedError

    def sync_client(self, client):
        raise NotImplementedError
