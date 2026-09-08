"""Development ASGI entry; installed runtime uses the factory without dev side effects."""

from solora.web.application import create_app as create_app

app = create_app()
