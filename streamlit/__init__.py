class _Secrets(dict):
    pass

secrets = _Secrets()

session_state = {}

class _Sidebar:
    def expander(self, *_, **__):
        return self
    def markdown(self, *_):
        pass

sidebar = _Sidebar()

def __getattr__(name):
    def _stub(*_, **__):
        return None
    return _stub
