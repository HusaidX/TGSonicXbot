# All rights reserved


import asyncio
import os
import random
import re
import time
import urllib.parse
from typing import Any

import aiohttp
from py_yt import Playlist, VideosSearch

from KartikMusic import config, logger
from KartikMusic.helpers import Track, utils

try:
    import yt_dlp
except ImportError:
    yt_dlp = None

# Use environment variables for configuration
API_URL = os.getenv("API_URL", "https://www.riteshyt.in").rstrip("/")
API_KEY = os.getenv("API_KEY", "riteshpermanent_51059fe1467bb92a2a457999")

DEFAULT_API_URL = API_URL
DEFAULT_API_KEY = API_KEY
CHUNK_SIZE = 65536  # 64 KB for fast initial buffering without overloading server

VIDEO_ID_REGEX = [
    re.compile(
        r"(?:youtube\.com/(?:watch\?v=|embed/|shorts/|live/)|youtu\.be/)([A-Za-z0-9_-]{11})",
        re.IGNORECASE,
    ),
    re.compile(r"(?:v=|\/)([0-9A-Za-z_-]{11})"),
]

YT_API_KEY = "AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8"
YT_CLIENT_VER = "2.20250101.01.00"
DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"

YT_PROFILES = [
    {
        "clientName": "WEB",
        "clientVersion": YT_CLIENT_VER,
        "clientId": "1",
        "origin": "https://www.youtube.com",
        "userAgent": DEFAULT_USER_AGENT,
    },
    {
        "clientName": "WEB_REMIX",
        "clientVersion": "1.20250101.01.00",
        "clientId": "67",
        "origin": "https://music.youtube.com",
        "userAgent": DEFAULT_USER_AGENT,
    },
    {
        "clientName": "TVHTML5",
        "clientVersion": "7.20250101.00.00",
        "clientId": "7",
        "origin": "https://www.youtube.com",
        "userAgent": "Mozilla/5.0 (SmartHub; SMART-TV; U; Linux/SmartTV) AppleWebKit/537.42 (KHTML, like Gecko) SmartTV Safari/537.42",
    },
    {
        "clientName": "MWEB",
        "clientVersion": "2.20250101.01.00",
        "clientId": "2",
        "origin": "https://m.youtube.com",
        "userAgent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Mobile/15E148 Safari/604.1",
    },
]


def extract_video_id(url_or_id: str) -> str:
    if not url_or_id:
        return ""
    val = str(url_or_id).strip()
    if len(val) == 11 and not any(c in val for c in " /?:&=#"):
        return val
    for reg in VIDEO_ID_REGEX:
        if m := reg.search(val):
            return m.group(1)
    return ""


def _safe_search_ytdlp(query: str) -> dict[str, Any]:
    """Local fallback using yt-dlp to search and extract video info."""
    if yt_dlp is None:
        return {"result": []}
    ydl_opts = {
        "format": "bestaudio/best",
        "noplaylist": True,
        "extract_flat": True,
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 6,
        "extractor_args": {"youtube": {"player_client": ["mweb", "ios", "android"]}},
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(f"ytsearch1:{query}", download=False)
            entries = info.get("entries", [])
            if entries and entries[0]:
                entry = entries[0]
                vidid = entry.get("id")
                title = entry.get("title", "Track")
                duration = entry.get("duration", 0)
                d_str = "00:00"
                if duration:
                    m, s = divmod(int(duration), 60)
                    h, m = divmod(m, 60)
                    d_str = f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
                thumbnails = entry.get("thumbnails", [])
                thumb = (
                    thumbnails[0]["url"].split("?")[0]
                    if thumbnails
                    else f"https://i.ytimg.com/vi/{vidid}/hqdefault.jpg"
                )
                return {
                    "result": [
                        {
                            "id": vidid,
                            "title": title,
                            "link": f"https://www.youtube.com/watch?v={vidid}",
                            "duration": d_str,
                            "thumbnails": [{"url": thumb}],
                        }
                    ]
                }
        except Exception:
            pass
    return {"result": []}


async def download_assistant(query: str, dl_type: str) -> str:
    """Helper to get stream URL from the API"""
    safe_query = urllib.parse.quote(query)
    ext = "mp3" if dl_type == "audio" else "mp4"
    if API_KEY:
        url = f"{API_URL}/downloads/{API_KEY}/{safe_query}.{ext}"
    else:
        url = f"{API_URL}/downloads/stream?query={safe_query}&dl_type={dl_type}"
    return url


class YouTube:
    """
    Universal media player and extractor supporting 80+ platforms.
    """

    PLATFORM_PATTERNS = [
        ("spotify", r"(?:open\.|music\.)?spotify\.com|spotify:"),
        ("applemusic", r"(?:music|itunes)\.apple\.com"),
        ("jiosaavn", r"(?:jiosaavn|saavn)\.com"),
        ("youtube", r"(?:youtube\.com|youtu\.be)"),
        ("soundcloud", r"soundcloud\.com"),
        ("deezer", r"deezer\.com"),
        ("gaana", r"gaana\.com"),
        ("resso", r"resso\.(?:com|link)"),
        ("tidal", r"tidal\.com"),
        ("audiomack", r"audiomack\.com"),
        ("bandcamp", r"bandcamp\.com"),
        ("boomplay", r"boomplay\.com"),
        ("mixcloud", r"mixcloud\.com"),
        ("anghami", r"anghami\.com"),
        ("wynk", r"wynk\.in"),
        ("hungama", r"hungama\.com"),
        (
            "amazonmusic",
            r"music\.amazon\.(?:com|in|co\.uk|de|fr|es|it|co\.jp|ca|com\.au|com\.br|com\.mx)",
        ),
        ("qobuz", r"qobuz\.com"),
        ("pandora", r"pandora\.com"),
        ("iheart", r"iheart\.com"),
        ("tunein", r"tunein\.com"),
        ("napster", r"napster\.com"),
        ("lastfm", r"last\.fm"),
        ("shazam", r"shazam\.com"),
        ("genius", r"genius\.com"),
        ("reverbnation", r"reverbnation\.com"),
        ("hearthisat", r"hearthis\.at"),
        ("anchor", r"anchor\.fm"),
        ("podcasts_apple", r"podcasts\.apple\.com"),
        ("podcasts_google", r"podcasts\.google\.com"),
        ("vimeo", r"vimeo\.com"),
        ("dailymotion", r"(?:dailymotion\.com|dai\.ly)"),
        ("bilibili", r"(?:bilibili\.com|b23\.tv)"),
        ("twitch", r"twitch\.tv"),
        ("kick", r"kick\.com"),
        ("rumble", r"rumble\.com"),
        ("streamable", r"streamable\.com"),
        ("okru", r"ok\.ru"),
        ("coub", r"coub\.com"),
        ("odysee", r"(?:odysee\.com|lbry\.tv)"),
        ("bitchute", r"bitchute\.com"),
        ("ted", r"ted\.com"),
        ("loom", r"loom\.com"),
        ("rutube", r"rutube\.ru"),
        ("archiveorg", r"archive\.org"),
        ("youku", r"youku\.com"),
        ("iqiyi", r"(?:iq\.com|iqiyi\.com)"),
        ("mxplayer", r"mxplayer\.in"),
        ("imdb", r"imdb\.com"),
        ("instagram", r"(?:instagram\.com|instagr\.am)"),
        ("tiktok", r"(?:tiktok\.com|douyin\.com)"),
        ("twitter", r"(?:twitter\.com|(?:^|[\/\.])x\.com)"),
        ("facebook", r"(?:facebook\.com|fb\.watch)"),
        ("pinterest", r"(?:pinterest\.com|pin\.it)"),
        ("reddit", r"reddit\.com"),
        ("snapchat", r"(?:snapchat\.com|story\.snapchat\.com)"),
        ("threads", r"threads\.net"),
        ("tumblr", r"tumblr\.com"),
        ("vk", r"vk\.com"),
        ("likee", r"likee\.(?:video|com)"),
        ("triller", r"triller\.co"),
        ("kwai", r"(?:kwai\.com|kwai-video\.com)"),
        ("sharechat", r"sharechat\.com"),
        ("moj", r"mojapp\.in"),
        ("josh", r"myjosh\.in"),
        ("bluesky", r"bsky\.app"),
        ("mastodon", r"(?:mastodon\.[a-z]+|mstdn\.[a-z]+)"),
        ("weibo", r"(?:weibo\.com|weibo\.cn)"),
        ("kuaishou", r"(?:kuaishou\.com|kwai\.com)"),
        ("patreon", r"patreon\.com"),
        ("discord", r"(?:discord\.com|discordapp\.com)"),
        ("line", r"(?:line\.me|linevoom\.line\.me)"),
        ("linkedin", r"linkedin\.com"),
        ("terabox", r"(?:terabox|1024tera)"),
        ("google_drive", r"drive\.google\.com"),
        ("dropbox", r"dropbox\.com"),
        ("onedrive", r"(?:onedrive\.live\.com|1drv\.ms)"),
        ("mediafire", r"mediafire\.com"),
        ("mega", r"mega\.(?:nz|io)"),
        ("yandex_disk", r"disk\.yandex\.(?:ru|com)"),
        ("catbox", r"(?:catbox\.moe|files\.catbox\.moe)"),
        ("qqmusic", r"(?:y\.qq\.com|qq\.com)"),
        ("netease", r"music\.163\.com"),
        ("kugou", r"kugou\.com"),
        ("kuwo", r"kuwo\.cn"),
        ("zingmp3", r"zingmp3\.vn"),
        ("nhaccuatui", r"nhaccuatui\.com"),
        ("joox", r"joox\.com"),
    ]

    def __init__(self, api_key: str | None = None, api_url: str | None = None):
        self.api_key = (
            api_key
            if api_key is not None
            else (
                os.environ.get("API_KEY")
                or os.environ.get("ALONE_API_KEY")
                or os.environ.get("RITESH_API_KEY")
                or API_KEY
            )
        )
        raw_url = (
            api_url
            or os.environ.get("API_URL")
            or os.environ.get("ALONE_API_URL")
            or os.environ.get("RITESH_API_URL")
            or API_URL
            or DEFAULT_API_URL
        )
        self.api_url = raw_url.rstrip("/")

        self.base = "https://www.youtube.com/watch?v="
        self.cookies = []
        self.checked = False
        self.cookie_dir = "KartikMusic/cookies"
        self.warned = False
        self._recent_prefetches = {}
        self._search_cache: dict[str, tuple[float, Track]] = {}
        self.regex = re.compile(
            r"(https?://)?(www\.|m\.|music\.)?"
            r"(youtube\.com/(watch\?v=|shorts/|playlist\?list=)|youtu\.be/)"
            r"([A-Za-z0-9_-]{11}|PL[A-Za-z0-9_-]+)([&?][^\s]*)?"
        )
        self.iregex = re.compile(
            r"https?://(?:www\.|m\.|music\.)?(?:youtube\.com|youtu\.be)"
            r"(?!/(watch\?v=[A-Za-z0-9_-]{11}|shorts/[A-Za-z0-9_-]{11}"
            r"|playlist\?list=PL[A-Za-z0-9_-]+|[A-Za-z0-9_-]{11}))\S*"
        )
        self.chunk_size = CHUNK_SIZE
        self._client = None

    async def get_client(self):
        if self._client is None or self._client.closed:
            self._client = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30.0, connect=5.0, sock_connect=5.0)
            )
        return self._client

    def _get_params(self, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        params = {}
        if self.api_key:
            params["api_key"] = self.api_key
        if extra:
            params.update({k: v for k, v in extra.items() if v is not None})
        return params

    def detect_platform(self, url_or_query: str) -> str:
        s = str(url_or_query).strip()
        if not s:
            return "generic"
        if s.startswith("spot_"):
            return "spotify"
        if re.match(r"^[a-zA-Z0-9_-]{11}$", s):
            return "youtube"
        for platform, pattern in self.PLATFORM_PATTERNS:
            if re.search(pattern, s, re.IGNORECASE):
                return platform
        if "http://" in s or "https://" in s:
            return "generic"
        return "youtube"

    def get_cookies(self):
        if not self.checked:
            os.makedirs(self.cookie_dir, exist_ok=True)
            for file in os.listdir(self.cookie_dir):
                if file.endswith(".txt"):
                    self.cookies.append(f"{self.cookie_dir}/{file}")
            self.checked = True
        if not self.cookies:
            if not self.warned:
                self.warned = True
                logger.warning("Cookies are missing; downloads might fail.")
            return None
        return random.choice(self.cookies)

    async def save_cookies(self, urls: list[str]) -> None:
        logger.info("Saving cookies from urls...")
        os.makedirs(self.cookie_dir, exist_ok=True)
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=15.0)
        ) as session:
            for idx, url in enumerate(urls):
                if not url:
                    continue
                if url.startswith(("http://", "https://")):
                    link = url
                else:
                    name = url.split("/")[-1]
                    link = "https://batbin.me/raw/" + name
                try:
                    async with session.get(link) as resp:
                        resp.raise_for_status()
                        file_path = f"{self.cookie_dir}/cookies_{idx}.txt"
                        with open(file_path, "wb") as fw:
                            fw.write(await resp.read())
                except Exception as e:
                    logger.warning(f"Failed to download cookie from {link}: {e}")
        self.checked = False
        self.cookies.clear()
        logger.info(f"Cookies saved in {self.cookie_dir}.")

    def valid(self, url: str) -> bool:
        if not url or not isinstance(url, str):
            return False
        s = url.strip()
        if not s:
            return False
        if bool(re.match(self.regex, s)):
            return True
        if s.startswith("spot_") or re.match(r"^[a-zA-Z0-9_-]{11}$", s):
            return True
        for _, pattern in self.PLATFORM_PATTERNS:
            if re.search(pattern, s, re.IGNORECASE):
                return True
        return bool(re.match(r"^https?://[^\s]+", s))

    def invalid(self, url: str) -> bool:
        if not url:
            return False
        for _, pattern in self.PLATFORM_PATTERNS:
            if re.search(pattern, url, re.IGNORECASE):
                return False
        return bool(re.match(self.iregex, url))

    def _clean_link(self, link: str):
        if not link:
            return ""
        link = str(link)
        if "&" in link and "youtube" in link:
            link = link.split("&")[0]
        if "?si=" in link:
            link = link.split("?si=")[0]
        elif "&si=" in link:
            link = link.split("&si=")[0]
        return link

    def get_stream_url(
        self, query_or_id: str, dl_type: str = "audio", quality: int = 720
    ) -> str:
        safe_query = urllib.parse.quote(str(query_or_id).strip())
        extension = "mp3" if dl_type == "audio" else "mp4"
        if self.api_key:
            return f"{self.api_url}/downloads/{self.api_key}/{safe_query}.{extension}"
        return f"{self.api_url}/download?query={safe_query}&dl_type={dl_type}&quality={quality}"

    async def download_track(
        self, link: str, chat_id: int | None = None, *args, **kwargs
    ) -> str | None:
        return await self.download(link, video=False)

    async def stream(
        self,
        video_id: str,
        video: bool = False,
        *args,
        **kwargs,
    ) -> str | None:
        return await self.download(video_id, video=video, *args, **kwargs)

    async def search(self, query: str, m_id: int, video: bool = False) -> Track | None:
        cache_key = f"{query.strip().lower()}_{int(video)}"
        now = time.time()
        cached = self._search_cache.get(cache_key)
        if cached and (now - cached[0]) < 300:
            base_track = cached[1]
            return Track(
                id=base_track.id,
                channel_name=base_track.channel_name,
                duration=base_track.duration,
                duration_sec=base_track.duration_sec,
                message_id=m_id,
                title=base_track.title,
                thumbnail=base_track.thumbnail,
                url=base_track.url,
                view_count=base_track.view_count,
                video=video,
            )

        client = await self.get_client()
        platform = self.detect_platform(query)
        is_url = bool(re.match(r"^https?://", query.strip()))

        def _fmt_duration(val: Any) -> str:
            if not val or val == "00:00":
                return "00:00"
            if isinstance(val, (int, float)):
                secs = int(val)
                m, s = divmod(secs, 60)
                h, m = divmod(m, 60)
                return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
            val_str = str(val).strip()
            if ":" in val_str:
                return val_str
            try:
                secs = int(float(val_str))
                m, s = divmod(secs, 60)
                h, m = divmod(m, 60)
                return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
            except Exception:
                return "00:00"

        def _store_and_return(trk: Track) -> Track:
            if len(self._search_cache) > 250:
                self._search_cache.clear()
            self._search_cache[cache_key] = (now, trk)
            return trk

        if is_url and platform != "youtube":
            try:
                params = self._get_params({"link": query})
                async with client.get(
                    f"{self.api_url}/details",
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data and data.get("title"):
                            vidid = data.get("id") or data.get("vidid")
                            dl_url = data.get("download_url") or ""
                            dl_match = re.search(
                                r"/([A-Za-z0-9_-]{11})(?:$|\?|\.|\/)", dl_url
                            )
                            if dl_match:
                                vidid = dl_match.group(1)

                            title = data.get("title", "Track")
                            dur_raw = (
                                data.get("duration_min")
                                or data.get("duration_string")
                                or data.get("duration_sec")
                                or data.get("duration")
                            )
                            duration = _fmt_duration(dur_raw)
                            thumb = data.get("thumb") or data.get("thumbnail", "")

                            if vidid and re.match(r"^[A-Za-z0-9_-]{11}$", vidid):
                                ytlink = f"https://www.youtube.com/watch?v={vidid}"
                                return _store_and_return(
                                    Track(
                                        id=vidid,
                                        channel_name=data.get("artist")
                                        or platform.capitalize(),
                                        duration=duration,
                                        duration_sec=utils.to_seconds(duration),
                                        message_id=m_id,
                                        title=title[:25],
                                        thumbnail=thumb
                                        or f"https://i.ytimg.com/vi/{vidid}/hqdefault.jpg",
                                        url=ytlink,
                                        view_count="",
                                        video=video,
                                    )
                                )
            except Exception as e:
                logger.error(f"Error fetching details for {query}: {e}")

        async def _from_api() -> Track | None:
            params = self._get_params({"query": query, "limit": 1})
            async with client.get(
                f"{self.api_url}/search",
                params=params,
                timeout=aiohttp.ClientTimeout(total=3.5),
            ) as response:
                if response.status == 200:
                    result_data = await response.json()
                    result = result_data.get("result")
                    if result:
                        data = result[0]
                        thumbs = data.get("thumbnails") or []
                        thumb = (
                            thumbs[-1].get("url", "").split("?")[0]
                            if thumbs
                            else f"https://i.ytimg.com/vi/{data.get('id')}/hqdefault.jpg"
                        )
                        return Track(
                            id=data.get("id"),
                            channel_name=data.get("channel", {}).get("name"),
                            duration=data.get("duration"),
                            duration_sec=utils.to_seconds(data.get("duration")),
                            message_id=m_id,
                            title=(data.get("title") or "Track")[:25],
                            thumbnail=thumb,
                            url=data.get("link"),
                            view_count=data.get("viewCount", {}).get("short"),
                            video=video,
                        )
            return None

        async def _from_innertube() -> Track | None:
            matches = await self._innertube_search(query, limit=1)
            if matches:
                item = matches[0]
                return Track(
                    id=item.get("id"),
                    channel_name=item.get("channel"),
                    duration=item.get("duration"),
                    duration_sec=item.get("duration_sec"),
                    message_id=m_id,
                    title=(item.get("title") or "Track")[:25],
                    thumbnail=item.get("thumbnail"),
                    url=item.get("url"),
                    view_count="",
                    video=video,
                )
            return None

        tasks = [
            asyncio.create_task(_from_api()),
            asyncio.create_task(_from_innertube()),
        ]
        try:
            for done in asyncio.as_completed(tasks, timeout=4.0):
                try:
                    trk = await done
                    if trk and trk.id:
                        for t in tasks:
                            if not t.done():
                                t.cancel()
                        return _store_and_return(trk)
                except Exception:
                    continue
        finally:
            for t in tasks:
                if not t.done():
                    t.cancel()

        try:
            _search = VideosSearch(query, limit=1, with_live=False)
            results = await asyncio.wait_for(_search.next(), timeout=3.5)
            if results and results["result"]:
                data = results["result"][0]
                return _store_and_return(
                    Track(
                        id=data.get("id"),
                        channel_name=data.get("channel", {}).get("name"),
                        duration=data.get("duration"),
                        duration_sec=utils.to_seconds(data.get("duration")),
                        message_id=m_id,
                        title=(data.get("title") or "Track")[:25],
                        thumbnail=data.get("thumbnails", [{}])[-1]
                        .get("url")
                        .split("?")[0],
                        url=data.get("link"),
                        view_count=data.get("viewCount", {}).get("short"),
                        video=video,
                    )
                )
        except Exception:
            pass

        try:
            res_local = await asyncio.to_thread(_safe_search_ytdlp, query)
            if res_local and res_local.get("result"):
                data = res_local["result"][0]
                return _store_and_return(
                    Track(
                        id=data.get("id"),
                        channel_name="YouTube",
                        duration=data.get("duration"),
                        duration_sec=utils.to_seconds(data.get("duration")),
                        message_id=m_id,
                        title=(data.get("title") or "Track")[:25],
                        thumbnail=data.get("thumbnails", [{}])[-1]
                        .get("url")
                        .split("?")[0],
                        url=data.get("link"),
                        view_count="",
                        video=video,
                    )
                )
        except Exception:
            pass

        return None

    async def playlist(
        self, limit: int, user: str, url: str, video: bool
    ) -> list[Track | None]:
        url = self._clean_link(url)
        client = await self.get_client()
        params = self._get_params({"link": url, "limit": limit})
        try:
            async with client.get(
                f"{self.api_url}/playlist",
                params=params,
                timeout=aiohttp.ClientTimeout(total=8),
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    videos = (
                        data.get("videos") or data.get("tracks") or data.get("result")
                    )
                    if videos:
                        tracks = []
                        for item in videos:
                            if isinstance(item, dict):
                                vid_id = item.get("id")
                                title = item.get("title") or item.get("name") or "Track"
                                duration = item.get("duration", "00:00")
                                thumb = (
                                    item.get("thumbnails", [{}])[-1].get("url")
                                    if item.get("thumbnails")
                                    else item.get("thumb", "")
                                )
                                track = Track(
                                    id=vid_id or title,
                                    channel_name=item.get("channel", {}).get("name", "")
                                    if isinstance(item.get("channel"), dict)
                                    else item.get("artist", ""),
                                    duration=duration,
                                    duration_sec=utils.to_seconds(duration),
                                    title=title[:25],
                                    thumbnail=thumb.split("?")[0] if thumb else "",
                                    url=item.get("link", "").split("&list=")[0]
                                    if item.get("link")
                                    else f"https://www.youtube.com/watch?v={vid_id}"
                                    if vid_id
                                    else url,
                                    user=user,
                                    view_count="",
                                    video=video,
                                )
                                tracks.append(track)
                        return tracks
        except Exception as e:
            logger.error(f"Error fetching playlist from API: {e}")

        tracks = []
        try:
            plist = await Playlist.get(url)
            for data in plist["videos"][:limit]:
                track = Track(
                    id=data.get("id"),
                    channel_name=data.get("channel", {}).get("name", ""),
                    duration=data.get("duration"),
                    duration_sec=utils.to_seconds(data.get("duration")),
                    title=data.get("title")[:25],
                    thumbnail=data.get("thumbnails")[-1].get("url").split("?")[0],
                    url=data.get("link").split("&list=")[0],
                    user=user,
                    view_count="",
                    video=video,
                )
                tracks.append(track)
        except Exception:
            pass
        return tracks

    async def prefetch(self, link: str, video: bool = False):
        return False

    async def _innertube_search(self, query: str, limit: int = 1) -> list[dict]:
        client = await self.get_client()
        for prof in YT_PROFILES:
            try:
                url = f"https://www.youtube.com/youtubei/v1/search?key={YT_API_KEY}"
                headers = {
                    "Content-Type": "application/json",
                    "User-Agent": prof["userAgent"],
                    "Accept": "*/*",
                    "Accept-Language": "en-US,en;q=0.9",
                    "X-YouTube-Client-Name": prof["clientId"],
                    "X-YouTube-Client-Version": prof["clientVersion"],
                }
                if prof.get("origin"):
                    headers["Origin"] = prof["origin"]
                    headers["Referer"] = prof["origin"] + "/"
                payload = {
                    "context": {
                        "client": {
                            "clientName": prof["clientName"],
                            "clientVersion": prof["clientVersion"],
                            "hl": "en",
                            "gl": "US",
                        }
                    },
                    "query": query,
                }
                async with client.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    if resp.status != 200:
                        continue
                    data = await resp.json()
                    tracks = []
                    stack = [data]
                    while stack and len(tracks) < limit:
                        curr = stack.pop()
                        if isinstance(curr, dict):
                            if "videoRenderer" in curr:
                                vr = curr["videoRenderer"]
                                vid = vr.get("videoId")
                                title = vr.get("title", {}).get(
                                    "simpleText"
                                ) or "".join(
                                    r.get("text", "")
                                    for r in vr.get("title", {}).get("runs", [])
                                )
                                dur_str = vr.get("lengthText", {}).get(
                                    "simpleText", "00:00"
                                )
                                thumbs = vr.get("thumbnail", {}).get("thumbnails", [])
                                thumb = (
                                    thumbs[-1]["url"].split("?")[0]
                                    if thumbs
                                    else f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"
                                )
                                channel = (
                                    "".join(
                                        r.get("text", "")
                                        for r in vr.get("ownerText", {}).get("runs", [])
                                    )
                                    or "YouTube"
                                )
                                if vid and title:
                                    tracks.append(
                                        {
                                            "id": vid,
                                            "title": title,
                                            "duration": dur_str,
                                            "duration_sec": utils.to_seconds(dur_str),
                                            "thumbnail": thumb,
                                            "channel": channel,
                                            "url": f"https://www.youtube.com/watch?v={vid}",
                                        }
                                    )
                            stack.extend(curr.values())
                        elif isinstance(curr, list):
                            stack.extend(curr)
                    if tracks:
                        return tracks
            except Exception:
                continue
        return []

    async def _fetch_innertube_mix(self, video_id: str, limit: int = 15) -> list[Track]:
        results: list[Track] = []
        client = await self.get_client()

        for profile in YT_PROFILES:
            try:
                url = f"https://www.youtube.com/youtubei/v1/next?key={YT_API_KEY}"
                headers = {
                    "Content-Type": "application/json",
                    "User-Agent": profile["userAgent"],
                    "Accept": "*/*",
                    "Accept-Language": "en-US,en;q=0.9",
                    "X-YouTube-Client-Name": profile["clientId"],
                    "X-YouTube-Client-Version": profile["clientVersion"],
                }
                if profile.get("origin"):
                    headers["Origin"] = profile["origin"]
                    headers["Referer"] = profile["origin"] + "/"
                payload = {
                    "context": {
                        "client": {
                            "clientName": profile["clientName"],
                            "clientVersion": profile["clientVersion"],
                            "hl": "en",
                            "gl": "US",
                        }
                    },
                    "playlistId": f"RD{video_id}",
                }
                async with client.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    if resp.status != 200:
                        continue
                    data = await resp.json()
                    contents = (
                        data.get("contents", {})
                        .get("twoColumnWatchNextResults", {})
                        .get("playlist", {})
                        .get("playlist", {})
                        .get("contents", [])
                    )
                    for item in contents:
                        renderer = item.get("playlistPanelVideoRenderer")
                        if not renderer:
                            continue
                        vid = renderer.get("videoId")
                        if not vid:
                            continue
                        title_data = renderer.get("title", {})
                        title = (
                            title_data.get("simpleText")
                            or "".join(
                                r.get("text", "") for r in title_data.get("runs", [])
                            )
                            or "Track"
                        )
                        channel_data = renderer.get(
                            "shortBylineText", {}
                        ) or renderer.get("longBylineText", {})
                        channel = (
                            "".join(
                                r.get("text", "") for r in channel_data.get("runs", [])
                            )
                            or "YouTube"
                        )
                        duration_str = (
                            renderer.get("lengthText", {}).get("simpleText") or "00:00"
                        )
                        thumbs = renderer.get("thumbnail", {}).get("thumbnails", [])
                        thumb = (
                            thumbs[-1]["url"].split("?")[0]
                            if thumbs
                            else f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"
                        )
                        results.append(
                            Track(
                                id=vid,
                                channel_name=channel,
                                duration=duration_str,
                                duration_sec=utils.to_seconds(duration_str),
                                title=title,
                                thumbnail=thumb,
                                url=f"https://www.youtube.com/watch?v={vid}",
                                user="Autoplay",
                                video=False,
                            )
                        )
                    if results:
                        break
            except Exception:
                continue
        return results

    async def get_recommendations(
        self, target: str, limit: int | None = None
    ) -> list[Track]:
        if not limit or limit <= 0:
            limit = getattr(config, "AUTO_PLAY_LIMIT", 15)
        target_clean = str(target).strip()
        if not target_clean:
            return []
        if len(target_clean) == 11 and not any(c in target_clean for c in " /?:"):
            url_to_use = f"https://www.youtube.com/watch?v={target_clean}"
            seed_id = target_clean
        else:
            url_to_use = target_clean
            seed_id = extract_video_id(url_to_use)

        if not url_to_use.lower().startswith(("http://", "https://")):
            try:
                matches = await self._innertube_search(url_to_use, limit=1)
                if matches:
                    url_to_use = matches[0]["url"]
                    seed_id = matches[0]["id"]
            except Exception:
                pass

        if not seed_id:
            try:
                search_track = await self.search(target_clean, 0)
                if search_track and search_track.id:
                    seed_id = search_track.id
                    url_to_use = f"https://www.youtube.com/watch?v={seed_id}"
            except Exception:
                pass

        if not seed_id:
            return []

        tracks = await self._fetch_innertube_mix(seed_id, limit=limit)
        seen = set()
        unique_tracks: list[Track] = []
        for t in tracks:
            if t.id == seed_id or t.url == url_to_use or t.id in seen:
                continue
            seen.add(t.id)
            unique_tracks.append(t)
            if len(unique_tracks) >= limit:
                break
        return unique_tracks

    async def get_related(
        self,
        video_id: str,
        chat_id: int | None = None,
        video: bool = False,
        max_duration: int = 0,
    ) -> Track | None:
        from KartikMusic import queue

        history = queue.get_autoplay_history(chat_id) if chat_id else []
        limit = getattr(config, "AUTO_PLAY_LIMIT", 15)
        if len(history) >= limit and chat_id:
            queue.clear_autoplay_history(chat_id)
            history = []

        tracks = await self.get_recommendations(video_id, limit=limit)
        if not tracks:
            return None

        candidates: list[Track] = [
            track
            for track in tracks
            if track.id != video_id
            and track.url != video_id
            and track.id not in history
            and track.url not in history
            and (max_duration <= 0 or track.duration_sec <= max_duration)
        ]

        if not candidates:
            if chat_id:
                queue.clear_autoplay_history(chat_id)
            candidates = [
                track
                for track in tracks
                if track.id != video_id
                and track.url != video_id
                and (max_duration <= 0 or track.duration_sec <= max_duration)
            ]

        if not candidates:
            return None

        random.shuffle(candidates)
        next_track = candidates[0]
        if chat_id:
            queue.add_autoplay_history(chat_id, video_id, next_track.id)

        next_track.video = video
        next_track.user = "Autoplay"
        return next_track

    async def download(
        self,
        video_id: str,
        video: bool = False,
        *args,
        **kwargs,
    ) -> str | None:
        raw_target = str(video_id).strip()
        is_url = bool(re.match(r"^https?://", raw_target))
        actual_id = raw_target
        if not is_url and not re.match(r"^[A-Za-z0-9_-]{11}$", raw_target):
            try:
                resolved_track = await self.search(raw_target, 0, video=video)
                if resolved_track and re.match(
                    r"^[A-Za-z0-9_-]{11}$", resolved_track.id
                ):
                    actual_id = resolved_track.id
            except Exception as e:
                logger.error(f"Error resolving video ID for {raw_target}: {e}")

        url = actual_id if is_url else (self.base + actual_id)
        dl_type = "video" if video else "audio"

        if self.api_key:
            safe_query = urllib.parse.quote(
                url if is_url else f"youtube.com/{actual_id}"
            )
            ext = "mp4" if video else "mp3"
            return f"{self.api_url}/downloads/{self.api_key}/{safe_query}.{ext}"

        return await download_assistant(url, dl_type)

    async def extract_async(self, url: str) -> dict[str, Any]:
        client = await self.get_client()
        async with client.get(
            f"{self.api_url}/api/get", params=self._get_params({"url": url})
        ) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def search_async(self, query: str, limit: int = 5) -> dict[str, Any]:
        client = await self.get_client()
        async with client.get(
            f"{self.api_url}/search",
            params=self._get_params({"q": query, "limit": limit}),
        ) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def details_async(self, link_or_id: str) -> dict[str, Any]:
        client = await self.get_client()
        async with client.get(
            f"{self.api_url}/details", params=self._get_params({"link": link_or_id})
        ) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def close(self):
        if self._client and not self._client.closed:
            await self._client.close()


# Consolidated Aliases and drop-in exports
AllSupport = YouTube
AloneAPI = YouTube
UniversalAPI = YouTube
all_support = YouTube(api_key=API_KEY, api_url=API_URL)

__all__ = [
    "API_KEY",
    "API_URL",
    "CHUNK_SIZE",
    "DEFAULT_API_KEY",
    "DEFAULT_API_URL",
    "AllSupport",
    "AloneAPI",
    "UniversalAPI",
    "YouTube",
    "all_support",
]
