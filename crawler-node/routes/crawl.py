from flask import Blueprint, request, jsonify
from utils.helpers import get_crawler_by_type

crawl_bp = Blueprint('crawl', __name__)

@crawl_bp.route('/crawl', methods=['POST'])
def crawl():
    try:
        data = request.get_json() or {}

        crawler_type = data.get("type")
        url = data.get("base_url")
        options = data.get("options", {})

        if not crawler_type or not url:
            return jsonify({"status": "error", "message": "Missing 'type' or 'url' in request"}), 400

        crawler = get_crawler_by_type(crawler_type)
        if not crawler:
            return jsonify({"status": "error", "message": f"Unknown crawler type '{crawler_type}'"}), 400

        result = crawler.crawl({
            "base_url": url,
            "options": options
        })

        if not isinstance(result, dict):
            return jsonify({"status": "error", "message": "Crawler did not return valid result"}), 500

        return jsonify(result)

    except Exception as e:
        return jsonify({"status": "error", "message": f"Unhandled server error: {str(e)}"}), 500
