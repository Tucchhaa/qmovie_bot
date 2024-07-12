import os

from playwright.async_api import async_playwright, BrowserContext, Browser, Page

from scrapper import MovieData, Scrapper

USER_DATA_DIR = f"{os.getcwd()}/chromium_user_data"


async def create_movie_fetcher(scrappers: list[Scrapper]):
    instance = MovieFetcher(scrappers)
    await instance.init()
    return instance


class MovieFetcher:
    def __init__(self, scrappers: list[Scrapper]):
        self.scrappers: list[Scrapper] = scrappers

        self.pw = None
        self.browsers_pool: list[BrowserContext] = []

    async def init(self):
        self.pw = await async_playwright().start()
        self.browsers_pool = await self.__create_browser_pool(1)

    async def __create_browser_pool(self, n: int) -> list[BrowserContext]:
        pool = []

        for i in range(n):
            context: BrowserContext = await self.pw.chromium.launch_persistent_context(
                headless=False,
                user_data_dir=USER_DATA_DIR,
                channel="chrome",
                java_script_enabled=True,
                viewport={"width": 1920, "height": 1080, },
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
                bypass_csp=True,
            )

            await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

            pool.append(context)

        return pool

    # todo: use task pool instead
    def __get_browser(self) -> BrowserContext:
        return self.browsers_pool[0]

    async def search_by_name(self, name: str) -> list[MovieData]:
        result = []

        for scrapper in self.scrappers:
            if not await scrapper.check_resource_availability():
                print(f"{scrapper.resource_name}: resource is unavailable")

                continue

            result += await scrapper.search_movies_by_name(name)

        return result

    async def get_movie_complete_info(self, movie: MovieData) -> MovieData:
        # TODO: change to work with multiple scrappers
        return await self.scrappers[0].scrap_movie_complete_info(movie)

    async def get_movie_link(self, movie: MovieData, dubbing: str, resolution: str) -> str:
        # TODO: change to work with multiple scrappers
        page: Page = await self.__get_browser().new_page()

        return await self.scrappers[0].scrap_movie_link(page, movie, dubbing, resolution)
