

class Service:
    """
    Service interface use to notify implemented services of users/permissions
    changes.
    TODO: Synch this interface with Magpie webhooks
    """
    def __init__(self, name):
        self.name = name

    def json(self):
        return {"name": self.name}

    def create_user(self, username):
        pass

    def delete_user(self, username):
        pass

    def set_permission(self, permission):
        pass

    def delete_permission(self, permission):
        pass
