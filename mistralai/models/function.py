class Function:
    def __init__(self, name='', description='', parameters=None):
        self.name = name
        self.description = description
        self.parameters = parameters or {}
