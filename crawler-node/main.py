from flask import Flask
from routes.health import health_bp
from routes.crawl import crawl_bp

app = Flask(__name__)

app.register_blueprint(health_bp)
app.register_blueprint(crawl_bp)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
