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
           return '', 401

        if not crawler_type or not url:
            send_result_to_laravel({
                "type": crawler_type,
                "original_url": url,
                "final_url": '',
                "error": 'Missing type or url in request',
                "meta": meta,
                "is_last": True,
                'status_code' : 400
                })
            return '', 400
           
        crawler = get_crawler_by_type(crawler_type)
        
        if not crawler:
            send_result_to_laravel({
                "type": crawler_type,
                "original_url": url,
                "final_url": '',
                "error": 'Unknown crawler type',
                "meta": meta,
                "is_last": True,
                'status_code' : 400
            }),
            return '', 400

        result = crawler.crawl(data)      

        return jsonify(result)

    except Exception as e:
            send_result_to_laravel({
                "type": crawler_type,
                "original_url": url,
                "final_url": '',
                "error": f"Unhandled server error: {str(e)}",
                "meta": meta,
                "is_last": True,
                'status_code' : 500
            })
            return '', 500        