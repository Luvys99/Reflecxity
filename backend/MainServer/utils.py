import uuid

def generate_uuid() -> str:
    return str(uuid.uuid4())

def is_allowed_file(filename: str, allowed_extensions: set) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions
