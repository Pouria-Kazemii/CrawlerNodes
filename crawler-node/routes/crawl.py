import threading
from flask import Blueprint, request, jsonify
from utils.helpers import get_crawler_by_type
from config import LARAVEL_API_TOKEN
from utils.sender import send_result_to_laravel

crawl_bp = Blueprint('crawl', __name__)

@crawl_bp.route('/crawl', methods=['POST'])
def crawl():
    try:
        data = request.get_json() or {}
        crawler_type = data.get("type")
        url = data.get("urls")
        meta = data.get('meta')

        auth_header = request.headers.get("Authorization", "")
        token = auth_header.replace("Bearer ", "").strip()

        if token != LARAVEL_API_TOKEN:
            send_result_to_laravel({
                "type": crawler_type,
                "original_url": url,
                "final_url": '',
                "error": 'Unauthorized request',
                "meta": meta,
                "is_last": True,
                'status_code': 401
            })
            return jsonify({'error': 'Unauthorized'}), 401

        if not crawler_type or not url:
            send_result_to_laravel({
                "type": crawler_type,
                "original_url": url,
                "final_url": '',
                "error": 'Missing type or urls in request',
                "meta": meta,
                "is_last": True,
                'status_code': 400
            })
            return jsonify({'error': 'Missing data'}), 400

        crawler = get_crawler_by_type(crawler_type)
        if not crawler:
            send_result_to_laravel({
                "type": crawler_type,
                "original_url": url,
                "final_url": '',
                "error": 'Unknown crawler type',
                "meta": meta,
                "is_last": True,
                'status_code': 400
            })
            return jsonify({'error': 'Unknown crawler type'}), 400

        threading.Thread(target=crawler.crawl, args=(data,)).start()

        return jsonify({'status': 'ok'}), 200

    except Exception as e:
        send_result_to_laravel({
            "type": data.get("type"),
            "original_url": data.get("urls"),
            "final_url": '',
            "error": f"Unhandled server error: {str(e)}",
            "meta": data.get('meta'),
            "is_last": True,
            'status_code': 500
        })
        return jsonify({'error': 'Internal server error'}), 500
