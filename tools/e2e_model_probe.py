#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DSH 配置条目端到端探针：GET /v1/models + POST /v1/chat/completions（流式，记首字）。
用法: python tools/e2e_model_probe.py --base URL --model ID [--api-key K] [--prompt 你好] [--max-tokens 64]
只打印一行 JSON。"""
import argparse, json, time, urllib.request, urllib.error

def get_models(base, key):
    url = base.rstrip('/') + '/models'
    req = urllib.request.Request(url)
    if key:
        req.add_header('Authorization', 'Bearer ' + key)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            body = r.read().decode('utf-8', 'replace')
            code = r.status
    except urllib.error.HTTPError as e:
        return e.code, [], e.read().decode('utf-8', 'replace')[:300]
    except Exception as e:
        return 0, [], type(e).__name__ + ': ' + str(e)[:200]
    try:
        ids = [m.get('id') for m in json.loads(body).get('data', [])]
    except Exception:
        ids = []
    return code, ids, body[:300]

def chat(base, model, key, prompt, max_tokens, timeout):
    url = base.rstrip('/') + '/chat/completions'
    payload = {
        'model': model,
        'messages': [{'role': 'user', 'content': prompt}],
        'max_tokens': max_tokens,
        'stream': True,
        'temperature': 0,
        'reasoning_effort': 'none',
    }
    req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), method='POST')
    req.add_header('Content-Type', 'application/json')
    if key:
        req.add_header('Authorization', 'Bearer ' + key)
    t0 = time.time()
    ttft = None
    parts = []
    code = 0
    err = ''
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            code = r.status
            for raw in r:
                line = raw.decode('utf-8', 'replace').strip()
                if not line.startswith('data:'):
                    continue
                data = line[5:].strip()
                if data == '[DONE]':
                    break
                try:
                    obj = json.loads(data)
                except Exception:
                    continue
                ch = (obj.get('choices') or [{}])[0]
                d = ch.get('delta') or {}
                piece = d.get('content') or ''
                if piece:
                    if ttft is None:
                        ttft = time.time() - t0
                    parts.append(piece)
    except urllib.error.HTTPError as e:
        code = e.code
        err = e.read().decode('utf-8', 'replace')[:400]
    except Exception as e:
        err = type(e).__name__ + ': ' + str(e)[:200]
    wall = time.time() - t0
    return code, ttft, wall, ''.join(parts), err

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', required=True)
    ap.add_argument('--model', required=True)
    ap.add_argument('--api-key', default='')
    ap.add_argument('--prompt', default='用一句话说明你是哪个模型。')
    ap.add_argument('--max-tokens', type=int, default=64)
    ap.add_argument('--timeout', type=float, default=180)
    a = ap.parse_args()
    mc, ids, mbody = get_models(a.base, a.api_key)
    code, ttft, wall, text, err = chat(a.base, a.model, a.api_key, a.prompt, a.max_tokens, a.timeout)
    row = {
        'base': a.base,
        'model': a.model,
        'models_http': mc,
        'models_ids': ids,
        'http': code,
        'ttft_s': None if ttft is None else round(ttft, 3),
        'wall_s': round(wall, 3),
        'text60': text[:60].replace('\n', ' '),
        'err': err,
    }
    print(json.dumps(row, ensure_ascii=False))

if __name__ == '__main__':
    main()
