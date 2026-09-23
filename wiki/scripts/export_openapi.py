"""Export registered routes without lifespan, network calls or real application data."""
import ast
import inspect
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
with tempfile.TemporaryDirectory(prefix='ops-wiki-schema-') as data_dir:
    os.environ['OPS_AGENT_DATA_DIR'] = data_dir
    os.environ['OPS_AGENT_ENV'] = 'test'
    os.environ['OPS_AGENT_SECRET_KEY'] = 'documentation-export-isolated-key-only'
    from app.api import app
    from app.api.middleware.authentication import PUBLIC_PATHS
    from fastapi.routing import APIRoute
    spec = app.openapi()
    schemas = spec.setdefault('components', {}).setdefault('schemas', {})
    spec['components']['securitySchemes'] = {'BearerAuth': {'type': 'http', 'scheme': 'bearer'}}
    spec['security'] = [{'BearerAuth': []}]
    for route in app.routes:
        if not isinstance(route, APIRoute) or not route.include_in_schema:
            continue
        source = ast.parse(inspect.getsource(route.endpoint))
        # Console handlers parse Request manually, so FastAPI omits their bodies.
        models = []
        for node in ast.walk(source):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == '_parse_request_model':
                model = route.endpoint.__globals__[node.args[1].id]
                body = model.model_json_schema(ref_template='#/components/schemas/{model}')
                schemas.update(body.pop('$defs', {}))
                schemas[model.__name__] = body
                models.append(model.__name__)
        for method in route.methods:
            op = spec['paths'][route.path][method.lower()]
            op['tags'] = [route.path.split('/')[2] if route.path.startswith('/api/') else 'health']
            if route.path in PUBLIC_PATHS:
                op['security'] = []
            if models:
                assert len(models) == 1
                op['requestBody'] = {'required': True, 'content': {'application/json': {'schema': {'$ref': '#/components/schemas/' + models[0]}}}}
            if '_streaming_response' in inspect.getsource(route.endpoint) or route.path == '/api/alerts/sse':
                op['responses']['200'] = {'description': 'Server-sent events; see the streaming guide.', 'content': {'text/event-stream': {'schema': {'type': 'string'}}}}
    spec['info']['description'] = 'Generated from registered Ops Agent routes. Middleware authentication, manually parsed request models and SSE media types are documented. WebSocket frames are described separately. Documentation viewer does not execute requests.'
    output = ROOT / 'wiki' / 'assets' / 'openapi.json'
    output.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + '\n')
    count = sum(len(item) for item in spec['paths'].values())
    print(f'Exported {len(spec["paths"])} paths / {count} operations')
