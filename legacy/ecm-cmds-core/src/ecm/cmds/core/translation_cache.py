import asyncio
import inspect
import json
import os
import sys
from pathlib import Path
from typing import Any
from typing import Iterable
from typing import List
from typing import Optional
from typing import Union

import pandas as pd
from googletrans import Translator


if sys.platform.startswith("win"):
    os.environ["GRPC_DEFAULT_SSL_ROOTS_FILE_PATH"] = r"C:\local\certs\root.crt"
    os.environ["REQUESTS_CA_BUNDLE"] = r"C:\local\certs\root.crt"
    os.environ["SSL_CERT_FILE"] = r"C:\local\certs\root.crt"


class JsonCacheTranslator:
    def __init__(
        self,
        cache_path: Union[str, Path],
        src: str = "ko",
        dest: str = "en",
        translator: Optional[Translator] = None,
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ):
        self.cache_file = Path(cache_path)
        self.src = src
        self.dest = dest
        self.translator = translator or Translator()
        self.loop = loop or asyncio.get_event_loop()
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        if self.cache_file.exists():
            with self.cache_file.open("r", encoding="utf-8") as f:
                self.cache = json.load(f)
        else:
            self.cache = {}

    def _save_cache(self):
        with self.cache_file.open("w", encoding="utf-8") as f:
            json.dump(self.cache, f, ensure_ascii=False, indent=2)

    def _do_translate(self, text: str) -> str:
        task = self.translator.translate(text, src=self.src, dest=self.dest)
        if inspect.iscoroutine(task):
            result = self.loop.run_until_complete(task)
        else:
            result = task
        return result.text

    def translate_text(self, text: str) -> str:
        if not isinstance(text, str) or not text:
            return text
        if text in self.cache:
            return self.cache[text]
        translated = self._do_translate(text)
        self.cache[text] = translated
        self._save_cache()
        return translated

    def translate_list(self, texts: Iterable[Any]) -> List[Any]:
        unseen = {t for t in texts if isinstance(t, str) and t and t not in self.cache}
        for t in unseen:
            self.cache[t] = self._do_translate(t)
        if unseen:
            self._save_cache()
        return [self.cache[t] if isinstance(t, str) and t in self.cache else t for t in texts]

    def translate_series(self, series: pd.Series) -> pd.Series:
        vals = series.dropna().unique()
        unseen = {t for t in vals if isinstance(t, str) and t not in self.cache}
        for t in unseen:
            self.cache[t] = self._do_translate(t)
        if unseen:
            self._save_cache()
        return series.map(lambda x: self.cache[x] if isinstance(x, str) and x in self.cache else x)



def translate_list_cached(texts: Iterable[Any], cache_path: Union[str, Path], src: str = "ko", dest: str = "en"):
    return JsonCacheTranslator(cache_path, src, dest).translate_list(texts)


def translate_series_cached(series: pd.Series, cache_path: Union[str, Path], src: str = "ko", dest: str = "en"):
    return JsonCacheTranslator(cache_path, src, dest).translate_series(series)


def translate_df_cached(df: pd.DataFrame, cache_path: Union[str, Path], src: str = "ko", dest: str = "en"):
    """
    Standalone function to translate all str cells in a DataFrame using JSON cache.
    """
    translator = JsonCacheTranslator(cache_path, src, dest)
    return df.applymap(lambda x: translator.translate_text(x) if isinstance(x, str) else x)
