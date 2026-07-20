import os

from app import create_app, db

app = create_app()

if __name__ == "__main__":
    # Never hardcode debug=True; use config/env only.
    app.run(debug=app.config.get('DEBUG', False), host='0.0.0.0', port=int(os.getenv('PORT', 5000)))
