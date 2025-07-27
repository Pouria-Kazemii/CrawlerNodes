from services.static_crawler import StaticCrawler
from services.dynamic_crawler import DynamicCrawler
from services.seed_crawler import SeedCrawler 
from services.authenticated_crawler import AuthenticatedCrawler 
# from services.api_crawler import ApiCrawler 
from services.paginated_crawler import PaginatedCrawler 
def get_crawler_by_type(crawler_type):
    match crawler_type:
        case "static":
            return StaticCrawler()
        case "dynamic":
            return DynamicCrawler()
        # case "api":
        #     return ApiCrawler()
        case "paginated":
            return PaginatedCrawler()
        case "seed":
            return SeedCrawler()
        case "authenticated":
            return AuthenticatedCrawler()
        case _:
            return None
