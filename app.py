import importlib
import os

from flask import Flask

import db

BLUEPRINT_MODULES = ["auth", "student", "staff", "admin", "db_view"]


def register_blueprints(app):
    registered = []
    for name in BLUEPRINT_MODULES:
        module_name = "routes." + name
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError as error:
            if error.name != module_name:
                raise
            continue
        app.register_blueprint(module.bp)
        registered.append(name)
    return registered


def register_error_handlers(app):
    @app.errorhandler(404)
    def not_found(error):
        return "<h1>404</h1><p>Page not found.</p>", 404

    @app.errorhandler(413)
    def too_large(error):
        return "<h1>413</h1><p>The uploaded file is too large (10 MB maximum).</p>", 413

    @app.errorhandler(500)
    def server_error(error):
        return "<h1>500</h1><p>Something went wrong on the server.</p>", 500


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_object("config")
    if test_config:
        app.config.update(test_config)

    os.makedirs(app.config["UPLOAD_DIR"], exist_ok=True)

    app.teardown_appcontext(db.close_db)
    app.config["REGISTERED_BLUEPRINTS"] = register_blueprints(app)
    register_error_handlers(app)
    return app


if __name__ == "__main__":
    create_app().run(debug=True)
