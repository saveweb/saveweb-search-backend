from functools import wraps
import asyncio
import os
import time

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

import meilisearch_python_sdk
import meilisearch_python_sdk.errors


MEILI_KEY = os.getenv('MEILI_KEY', '')
print('$MEILI_KEY', 'set' if MEILI_KEY else 'not set')
MEILI_URL = os.getenv('MEILI_URL', 'http://127.0.0.1:7700')
print('$MEILI_URL', MEILI_URL)
STWP_SEARCH_MAX_LOAD = float(os.getenv('STWP_SEARCH_MAX_LOAD')) if os.getenv('STWP_SEARCH_MAX_LOAD') else (
    os.cpu_count() / 1.5 if os.cpu_count() else 1.5
)
print('$STWP_SEARCH_MAX_LOAD', STWP_SEARCH_MAX_LOAD)
STWP_SEARCH_MAX_FLYING_OPS = int(os.getenv('STWP_SEARCH_MAX_FLYING_OPS')) if os.getenv('STWP_SEARCH_MAX_FLYING_OPS') else (
    int(STWP_SEARCH_MAX_LOAD * 2)
)
STWP_SEARCH_MAX_FLYING_OPS = STWP_SEARCH_MAX_FLYING_OPS if STWP_SEARCH_MAX_FLYING_OPS >= 1 else 1
print('$STWP_SEARCH_MAX_FLYING_OPS', STWP_SEARCH_MAX_FLYING_OPS)
STWP_SEARCH_CORS = os.getenv('STWP_SEARCH_CORS', ','.join([
    # 'https://search.saveweb.org',
    '*'
]))
print('$STWP_SEARCH_CORS', STWP_SEARCH_CORS)

app = FastAPI()
# set CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=STWP_SEARCH_CORS.split(','),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
index_name = "entry"


async def get_load():
    with open('/proc/loadavg', 'r') as f:
        load = f.read().split()[0]
    return float(load)

def load_limiter(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        if await get_load() > STWP_SEARCH_MAX_LOAD:
            print('[INFO] 荷载过高')
            return JSONResponse({
                'hits': [
                    {
                        'title': '丑搜当前荷载过高，请稍后再试',
                        'content': '服务器荷载过高，请稍后再试。原因：1. 数据库正在更新全文索引 2. 服务器没有摸鱼，在干其它重荷载的任务',
                        'author': ';丑搜',
                        'date': int(time.time()),
                        'link': '#',
                    },
                ],
                'error': '丑搜当前荷载过高，请稍后再试',
            }, status_code=503, headers={'Retry-After': '30'})
        return await func(*args, **kwargs)
    return wrapper

flying_ops = 0
def ops_limiter(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        global flying_ops
        if flying_ops >= STWP_SEARCH_MAX_FLYING_OPS:
            print('[INFO] 操作过多')
            return JSONResponse({
                'hits': [
                    {
                        'title': '飞行中的搜索过多，请稍后再试',
                        'content': '同一时间内的搜索请求过多。请稍后再试。',
                        'author': ';丑搜',
                        'date': int(time.time()),
                        'link': '#',
                    },
                ],
                'error': '操作过多，请稍后再试',
            }, status_code=503, headers={'Retry-After': '30'})
        flying_ops += 1
        try:
            return await func(*args, **kwargs)
        finally:
            flying_ops -= 1
    return wrapper


client = meilisearch_python_sdk.AsyncClient(MEILI_URL, MEILI_KEY)


@app.get('/api/')
async def go_back_home():
    # redirect to /
    return Response(status_code=302, headers={'Location': '/'})

@app.get('/api/entry/{entry_id}')
@load_limiter
@ops_limiter
async def article(entry_id: int):
    results = {}
    results['data'] = await client.index(index_name).get_document(entry_id)
    results['humans.txt'] = 'is_favorite 目前与主数据库不同步'

    return results

@app.get('/api/stats')
@app.head('/api/stats')
@load_limiter
@ops_limiter
async def stats():
    stats = await client.index(index_name).get_stats()
    return stats

    
    

@app.get('/api/search')
@load_limiter
@ops_limiter
async def search(q: str = 'saveweb', p: int = 0, f: str = 'false', h: str = 'false'):
    query = q  # 搜索词
    page = p  # 0-based
    fulltext = f  # 返回全文（搜索还是以全文做搜索，只是返回的时候限制一下长度）
    highlight = h  # 是否高亮

    print(query, page, 'fulltext:', fulltext, 'highlight:', highlight)
    with open('search.log', 'a') as fio:
        fio.write(query + '\t' + str(page) + '\n')

    # 搜空，返空
    if not query:
        return JSONResponse({
            'error': '搜索词为空',
        }, status_code=400)

    opt_params = {
        'limit': 10,
        'offset': 10 * page,
        'attributes_to_retrieve': ['id', 'id_feed', 'title', 'content', 'link', 'date', 'tags', 'author', 'lastSeen'],
    }

    if fulltext != 'true':
        opt_params['attributes_to_crop'] = ['content']
        opt_params['crop_length'] = 120

    if highlight == 'true':
        opt_params['attributes_to_highlight'] = ['title', 'content', 'date', 'tags', 'author']
        opt_params['highlight_pre_tag'] = '<span class="uglyHighlight text-purple-500">'
        opt_params['highlight_post_tag'] = '</span>'

    # 第一次搜索
    try:
        _results = await client.index(index_name).search(query, **opt_params)
    except meilisearch_python_sdk.errors.MeilisearchError as e:
        print('数据库错误', e)
        return {
            'hits': [
                {
                    'title': '数据库错误',
                    'content': '查询数据库时出错。如果一直出现这个错误，说明数据库寄了，请反馈。',
                    'author': ';丑搜',
                    'date': int(time.time()),
                    'link': '#',
                },
            ],
            'error': '数据库错误',
        }

    lengths : dict[str, int]= {}
    if fulltext != 'true':  # 再搜索一次，获取全文长度
        opt_params = {
            'limit': 10,
            'offset': 10 * page,
            'attributes_to_retrieve': ['id', 'id_feed', 'title', 'content', 'link', 'date', 'tags', 'author', 'lastSeen'],
        }
        _results2 = await client.index(index_name).search(query, **opt_params)
        for hit in _results2.hits:
            lengths.update({str(hit['id']): len(hit['content'])})

    # replace the hit with _formatted
    for hit in _results.hits:
        if fulltext != 'true':
            assert lengths != {}
            if str(hit['id']) in lengths:
                hit['content_length'] = lengths[str(hit['id'])]
        else:
            hit['content_length'] = len(hit['content'])
        if '_formatted' in hit:
            hit.update(hit['_formatted'])
            del hit['_formatted']

    results = {
        'hits': _results.hits,
        'estimatedTotalHits': _results.estimated_total_hits, #TODO: estimatedTotalHits 改为 estimated_total_hits
        'humans.txt': '使用 API 时请检查 error 字段，高荷载/出错时会返回它。is_favorite 字段目前与主数据库不同步，只有在全库重新索引时才会更新。',
    }

    return results

@app.route('/')
async def root(request):
    return HTMLResponse(open('templates/index.html', 'r').read()) # 反正只有一个页面

async def main():
    import hypercorn.asyncio
    config = hypercorn.Config()
    config.bind = ['[::]:8077']
    await hypercorn.asyncio.serve(app, config)

if __name__ == '__main__':
    # hypercorn --bind '[::]:8077' saveweb-search-backend:app
    asyncio.run(main())