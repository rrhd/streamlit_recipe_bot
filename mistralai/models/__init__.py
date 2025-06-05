class SystemMessage:
    def __init__(self, content=""):
        self.role = "system"
        self.content = content
class UserMessage:
    def __init__(self, content=""):
        self.role = "user"
        self.content = content
class AssistantMessage:
    def __init__(self, content=""):
        self.role = "assistant"
        self.content = content
class ToolMessage:
    def __init__(self, tool_call_id="", content=""):
        self.role = "tool"
        self.tool_call_id = tool_call_id
        self.content = content
class TextChunk:
    def __init__(self, text=""):
        self.type = "text"
        self.text = text
class ImageURLChunk:
    def __init__(self, image_url=None):
        self.image_url = image_url or {}
class Function:
    def __init__(self, name="", description="", parameters=None):
        self.name = name
        self.description = description
        self.parameters = parameters or {}
class Tool:
    def __init__(self, *, type="function", function=None):
        self.type = type
        self.function = function
class ToolChoice:
    def __init__(self, function=None):
        self.type = "function"
        self.function = function or {}
