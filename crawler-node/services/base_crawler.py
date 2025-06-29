from abc import ABC, abstractmethod

class BaseCrawler(ABC):
    @abstractmethod
    def crawl(self, url, options=None):
        pass
