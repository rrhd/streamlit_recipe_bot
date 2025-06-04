class BaseMessage:
    def __init__(self, content=None):
        self.content = content
        self.role = ""
        self.tool_calls = None

class SystemMessage(BaseMessage):
    def __init__(self, content=None):
        super().__init__(content)
        self.role = "system"

class UserMessage(BaseMessage):
    def __init__(self, content=None):
        super().__init__(content)
        self.role = "user"

class AssistantMessage(BaseMessage):
    def __init__(self, content=None, tool_calls=None):
        super().__init__(content)
        self.role = "assistant"
        self.tool_calls = tool_calls

class ToolMessage(BaseMessage):
    def __init__(self, tool_call_id=None, content=None):
        super().__init__(content)
        self.role = "tool"
        self.tool_call_id = tool_call_id

class TextChunk:
    def __init__(self, text="", type="text"):
        self.text = text
        self.type = type

class ImageURLChunk:
    def __init__(self, image_url=None):
        self.image_url = image_url
        self.type = "image_url"
