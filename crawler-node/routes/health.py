from flask import Blueprint, jsonify
import datetime

health_bp = Blueprint('health', __name__)

@health_bp.route('/health')
def health():
    return jsonify({
        "status": "ok",
        "node": "node-1",
        "time": datetime.datetime.utcnow().isoformat() + "Z"
    })
