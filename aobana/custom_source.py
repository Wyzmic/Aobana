import os
import posixpath
import re
from urllib.parse import unquote, urlsplit

TAG = re.compile(r' [0-9a-f]{32}$')
UUID = r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
WRAPPER = re.compile(UUID + '_ExportBlock-' + UUID)


def clean_name(name, extension=False):
    stem, suffix = os.path.splitext(name) if extension else (name, '')
    return TAG.sub('', stem) + suffix


def clean_path(path):
    parts = path.replace(chr(92), '/').split('/')
    return '/'.join(clean_name(p, i == len(parts) - 1) for i, p in enumerate(parts)
                    if not WRAPPER.fullmatch(p))


def natural_key(name):
    from aobana.search.titles import get_sort_key
    parts = []
    for piece in re.split(r'(\d+)', name):
        if piece.isdecimal():
            digits = str(int(piece))
            parts.append('1' + f'{len(digits):08d}' + digits)
        else:
            parts.append('0' + get_sort_key(piece).hex())
    return '/'.join(parts) + '/' + get_sort_key(name).hex()


def position_key(order):
    return '/'.join(f'{int(n):012d}' if isinstance(n, (int, float)) or str(n).isdigit() else str(n)
                    for n in order or [])


def source_key(category, positions=None, fallback=''):
    return natural_key(fallback) if positions is None else natural_key(category) + '/2' + position_key(positions)


def link_target(page, target):
    url = urlsplit(target)
    if url.scheme or url.netloc or not url.path or url.path.startswith(('/', chr(92))):
        return None
    path = posixpath.normpath(posixpath.join(posixpath.dirname(page), unquote(url.path)))
    if path == '..' or path.startswith('../') or chr(92) in path:
        return None
    return clean_path(path)


def page_body(text, meta):
    from aobana.indexing.custom_markdown import parse
    return parse(text, meta['title'], meta['navigation'])


class Catalog:

    def __init__(self, files):
        from aobana import utils
        from aobana.indexing.custom_markdown import links, parse
        from aobana.indexing.subtitle_input import decode_bytes
        self.meta = {}
        self.parents = {}
        self.missing = []
        self.files = {}
        documents = {}
        identities = {}
        markdown = [(path, utils.name_key(relpath)) for path, relpath in files if relpath.lower().endswith('.md')]
        counts = {}
        for _, key in markdown:
            counts[clean_path(key)] = counts.get(clean_path(key), 0) + 1
        for path, key in markdown:
            normalized = clean_path(key)
            if counts[normalized] > 1:
                # Two pages of one title in one folder (Notion's "Untitled"): both keep their ID.
                normalized = posixpath.join(posixpath.dirname(normalized), posixpath.basename(key))
            if normalized in identities:
                normalized = key
            identities[normalized] = key
            self.files[key] = path
            with open(path, 'rb') as handle:
                text = decode_bytes(handle.read())[0]
            documents[key] = (normalized, text)
        directories = {posixpath.dirname(name) for name in identities}
        directories |= {name[:i] for name in list(directories) for i, c in enumerate(name) if c == '/'}
        pairs = {key: posixpath.splitext(name)[0] for key, (name, _) in documents.items()
                 if posixpath.splitext(name)[0] in directories}
        redundant = {folder.split('/')[0] for folder in pairs.values()
                     if len(folder.split('/')) == 2 and folder.split('/')[0] == folder.split('/')[1]}

        def logical(name):
            parts = name.split('/')
            if len(parts) > 1 and parts[0] in redundant:
                parts.pop(0)
            return '/'.join(parts)

        self.logical = logical
        edges = {}
        for key, (name, text) in documents.items():
            title = posixpath.splitext(clean_name(posixpath.basename(name), True))[0]
            child_folder = pairs.get(key)
            ordered, navigation = [], set()
            for label, target, whole in links(text):
                target_name = link_target(name, target)
                if not target_name or not target_name.lower().endswith('.md'):
                    continue
                expected_folder = posixpath.splitext(name)[0]
                if not target_name.startswith(expected_folder + '/'):
                    continue
                navigation.add(target)
                raw_target = posixpath.normpath(posixpath.join(posixpath.dirname(key), unquote(urlsplit(target).path)))
                child = identities.get(target_name) or (raw_target if raw_target in documents else None)
                if child is None:
                    self.missing.append({'parent': key, 'target': target})
                elif child not in ordered:
                    ordered.append(child)
            if ordered:
                self.parents[key] = ordered
                for index, child in enumerate(ordered):
                    edges.setdefault(child, (key, index))
            empty = bool(child_folder) and not parse(text, title, navigation)[0]
            view = (child_folder + '/' + posixpath.basename(name)) if child_folder else name
            view = logical(view)
            category = view.split('/')[0] if '/' in view else title
            self.meta[key] = dict(path=view, category=category, title=title, folder_page=int(empty),
                                  paired_folder=logical(child_folder) if child_folder else None,
                                  navigation=navigation)
        # A page's paired folder by its path: the nearest one above a page is found by its path's
        # folders, not by testing every page against every folder (×20 from 4,000 to 16,000 files)
        paired = {}
        for page, meta in self.meta.items():
            if meta['paired_folder']:
                paired.setdefault(meta['paired_folder'], []).append(page)

        def paired_parent(key):
            folder = self.meta[key]['path']
            while '/' in folder:
                folder = folder.rpartition('/')[0]
                parent = next((p for p in paired.get(folder, ()) if p != key), None)
                if parent is not None:
                    return parent
            return None
        cache = {}

        def ranks(key, active=()):
            if key in cache:
                return cache[key]
            if key in active:
                raise ValueError('Circular Markdown subpage order: ' + key)
            if key in edges:
                parent, index = edges[key]
                value = ranks(parent, (*active, key)) + [index]
            else:
                parent = paired_parent(key)
                if parent is not None:
                    value = ranks(parent, (*active, key)) + [999999999999, natural_key(self.meta[key]['path'])]
                else:
                    value = []
            cache[key] = value
            return value
        for key, meta in self.meta.items():
            vector = ranks(key)
            meta['order_key'] = source_key(meta['category'], vector, meta['path']) if vector or meta['paired_folder'] else natural_key(meta['path'])

    def get(self, path):
        from aobana.utils import name_key
        return self.meta.get(name_key(path))

    def rows(self, path):
        from aobana.indexing.subtitle_input import decode_bytes
        from aobana.utils import name_key
        with open(self.files[name_key(path)], 'rb') as handle:
            return page_body(decode_bytes(handle.read())[0], self.get(path))
