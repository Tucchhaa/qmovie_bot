import abc
import json

import requests
from playwright.async_api import Page

from bs4 import BeautifulSoup
from requests import Session

PLAYER_SELECTOR = "#oframecdnplayer"
DUBBING_BTN_CLASS = "b-translator__item"
DUBBING_BTN_SELECTOR = f".{DUBBING_BTN_CLASS}"
RESOLUTION_BTN_SELECTOR = "pjsdiv[f2id]"
PLAY_BTN_SELECTOR = "#oframecdnplayer > pjsdiv:nth-child(20) > pjsdiv:nth-child(1) > pjsdiv"
PLAYER_SETTINGS_BTN_SELECTOR = "#oframecdnplayer > pjsdiv:nth-child(17) > pjsdiv:nth-child(3)"
PLAYER_RESOLUTION_BTN_SELECTOR = "#cdnplayer_settings > pjsdiv > pjsdiv:nth-child(1)"


class ScrapperResolutionNotFoundException(Exception):
    def __init__(self, resolution: str):
        self.resolution = resolution


class ScrapperException(Exception):
    def __init__(self, message: str):
        self.message = message

    def __str__(self):
        return self.message


class MovieData:
    def __init__(self, name: str, image_url: str, info: str, link: str):
        self.name = name
        self.image_url = image_url
        self.info = info
        self.link = link

        self.dubbings = []
        self.resolutions = []

    def to_dict(self):
        return {
            "name": self.name,
            "image_url": self.image_url,
            "info": self.info,
            "link": self.link,
            "dubbings": self.dubbings,
            "resolutions": self.resolutions,
        }


class Scrapper(abc.ABC):
    resource_name = ":Abstract:"

    def __init__(self):
        self.base_headers = {
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'accept-encoding': 'zip, deflate, br, zstd',
            'accept-language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7;',
            'cache-control': 'no-cache',
            'sec-fetch-dest': 'document',
            'sec-fetch-site': 'same-origin',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-user': '?1',
            'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
        }

        self._sessions_pool: [Session] = []

    def get_session(self) -> Session:
        # TODO: enhance session logic
        if len(self._sessions_pool) == 0:
            self._sessions_pool.append(requests.session())

        return self._sessions_pool[0]

    @abc.abstractmethod
    async def check_resource_availability(self) -> bool: pass

    @abc.abstractmethod
    async def search_movies_by_name(self, name: str) -> list[MovieData]: pass

    @abc.abstractmethod
    async def scrap_movie_complete_info(self, movie: MovieData) -> MovieData: pass

    @abc.abstractmethod
    async def scrap_movie_link(self, page: Page, movie: MovieData, dubbing: str, resolution: str): pass


class RezkaScrapper(Scrapper):
    resource_name = "HDRezka"

    def __init__(self):
        super().__init__()
        self.base_url = "https://hdrezka.ag"
        self.search_url = f"{self.base_url}/search/?do=search&subaction=search&q="

    async def check_resource_availability(self) -> bool:
        session = self.get_session()

        response = session.get(self.base_url)

        return response.status_code != 200

    async def search_movies_by_name(self, name: str) -> list[MovieData]:
        session = self.get_session()

        response = session.get(f"{self.search_url}{name}", headers=self.base_headers)

        results = []

        if response.status_code != 200:
            return results

        soup = BeautifulSoup(response.text, "html.parser")

        for element in soup.find_all('div', class_='b-content__inline_item', limit=10):
            content_div = element.find('div', class_="b-content__inline_item-link")
            cover_div = element.find('div', class_="b-content__inline_item-cover")

            name: str = content_div.find('a').text.strip()
            link: str = content_div.find('a').get('href')
            info: str = content_div.find('div').text.strip()

            image_url: str = cover_div.find('img').get('src')

            results.append(MovieData(name, image_url, info, link))

        return results

    async def scrap_movie_complete_info(self, movie: MovieData) -> MovieData:
        session = self.get_session()

        response = session.get(movie.link, headers=self.base_headers)

        if response.status_code != 200:
            return movie

        soup = BeautifulSoup(response.text, 'html.parser')

        for element in soup.find_all('li', class_=DUBBING_BTN_CLASS):
            dubbing = element.text.strip()
            movie.dubbings.append(dubbing)

        if len(movie.dubbings) == 0:
            movie.dubbings.append("По умолчанию")

        movie.resolutions = ['360p', '480p', '720p', '1080p', '1080p Ultra']

        return movie

    async def scrap_movie_link(self, page: Page, movie: MovieData, dubbing: str, resolution: str):
        result = ""

        def handle_request(request):
            nonlocal result

            index = request.url.find(":hls:manifest")

            if result == "" and index != -1:
                result = request.url[:index]
                print("RESULT: " + result)

        page.on("request", handle_request)

        await page.goto(movie.link)
        await page.wait_for_selector(PLAYER_SELECTOR)
        await page.wait_for_timeout(100)

        if dubbing != "По умолчанию":
            dubbingClicked = await page.evaluate(
                """
                (params) => {
                    var [dubbing, selector] = params
                    var elems = document.querySelectorAll(selector)
                    
                    var dubbingBtn = [...elems].filter(elem => elem.innerText.trim() === dubbing);
                
                    if (dubbingBtn.length == 0)
                        return false;
                        
                    dubbingBtn = dubbingBtn[0];
                    
                    dubbingBtn.click();
                    
                    return true;
                }
                """,
                [dubbing, DUBBING_BTN_SELECTOR]
            )

            if not dubbingClicked:
                raise Exception("не удалось кликнуть на дубляж")

            await page.wait_for_selector(PLAY_BTN_SELECTOR)
            await page.wait_for_timeout(100)

        await page.click(PLAYER_SETTINGS_BTN_SELECTOR)
        await page.wait_for_timeout(50)

        await page.click(PLAYER_RESOLUTION_BTN_SELECTOR)
        await page.wait_for_timeout(50)

        resolutionClicked = await page.evaluate(
            """
            (params) => {
                var [resolution, selector] = params
                var elems = document.querySelectorAll(selector);
                
                var resolutionBtn = [...elems].filter(elem => elem.innerText.trim() === resolution);
                
                if (resolutionBtn.length == 0)
                    return false;
                    
                resolutionBtn = resolutionBtn[0];
                
                resolutionBtn.click();
                
                return true;
            }
            """,
            [resolution, RESOLUTION_BTN_SELECTOR]
        )

        if not resolutionClicked:
            raise ScrapperResolutionNotFoundException(resolution)

        await page.wait_for_timeout(50)

        await page.close()

        if result == "":
            raise Exception("не удалось получить ссылку")

        return result





