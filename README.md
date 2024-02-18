# saveweb-search-backend

## Installation

```bash
pip install -r requirements.txt
```

## Setup environment variables

```bash
MEILI_KEY # MeiliSearch API key.
# default: '' (empty string)
MEILI_HOST # MeiliSearch host.
# default: "http://localhost:7700"
STWP_SEARCH_MAX_LOAD # If the load is higher than this, API will return 503.
# default: cpu_count / 1.5
STWP_SEARCH_MAX_FLYING_OPS # If the number of flying requests is higher than this, API will return 503.
# default: $STWP_SEARCH_MAX_LOAD * 2 (min value: 1)
STWP_SEARCH_CORS # CORS Allow-Origin header, split by `,`
# default: *
```

## Run

```bash
python saveweb-search-backend.py
# or
hypercorn --bind '[::]:8077' saveweb-search-backend:app # to customize the bind address
```
