"""Mount the archived cookbook dependency with only its SDK construction injected."""
from pathlib import Path
from fastapi import Depends, FastAPI


def create_baseline(sdk, source_file="evidence/fastapi-auth-source.md"):
    markdown = (Path(__file__).parent / source_file).read_text()
    source = markdown.split('```python', 1)[1].split('\n', 1)[1].split('```', 1)[0]
    construction = 'unkey = Unkey(root_key=os.environ["UNKEY_ROOT_KEY"])'
    assert source.count(construction) == 1
    source = source.replace(construction, 'unkey = supplied_sdk')
    # Only the reviewed Python dependency snippet; never execute other page content.
    scope = {'supplied_sdk': sdk}
    exec(compile(source, 'archived_cookbook_dependency.py', 'exec'), scope)
    application = FastAPI()

    @application.get('/items')
    def items(verification=Depends(scope['require_key']())):
        return {'items': []}

    return application
