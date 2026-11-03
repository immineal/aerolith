# aerolith (Python package)

The [Aerolith](https://github.com/immineal/aerolith) CSS, its optional JS and the Bryce-rendered
sprites, packaged as static files for Python web apps. There is no Python logic beyond telling
you where the files are.

```sh
pip install aerolith
```

**Django:** add `"aerolith"` to `INSTALLED_APPS`, then

```html
<link rel="stylesheet" href="{% static 'aerolith/aerolith.css' %}">
<script src="{% static 'aerolith/aerolith.js' %}" defer></script>
```

**FastAPI / Starlette:**

```python
from fastapi.staticfiles import StaticFiles
from aerolith import static_dir
app.mount("/aerolith", StaticFiles(directory=static_dir()), name="aerolith")
```

**Flask:**

```python
from flask import Blueprint
from aerolith import static_dir
app.register_blueprint(Blueprint("aerolith", __name__, static_folder=static_dir(),
                                 static_url_path="/aerolith"))
```

Then link `/aerolith/aerolith.css`. Components and markup: see the
[showcase](https://immineal.github.io/aerolith/) and the main README.
