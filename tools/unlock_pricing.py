#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'''unlock_pricing.py - 解锁定价实验（A/B）一条命令。

用途：同一份长 prompt 跑两臂 —— A) 默认；B) 加 --no-prefill-a8（全部走 A16）。
  从两臂的 TTFT 反解 f（prefill 里 A16/FP32-累加 MMA 的时间占比），
  再按 S = 1/(1-0.3842*f_eff) 估计解锁后的 prefill/tok-s 与 TTFT，最后给 GO / NO-GO。

重要方向性（别读反了）：
  B 组比 A 组越慢 => int8 通路帮得越多 => A16 占比 f 越小 => 解锁越没用。
  反之 B 几乎不掉速 => prefill 本来就在被钳的 A16 上 => 解锁收益最大。
  f>=0.60 等价于 B >= 715 tok/s（当 A 基线为 963）。

只用标准库；不碰 8080/8081/8091/8092 等他人端口（默认 18080，且端口被占直接报错退出）。
自检（不连引擎、不占卡）：  python unlock_pricing.py --selftest
'''

import argparse
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
import urllib.error

R_INT8_VS_A16 = 0.87    # int8 比 A16 快 1.87x => 同一份工作少花 0.87 份时间
UNLOCK_FACTOR = 1.624   # 本卡实测 76.71/47.24（BF16/FP32-acc，2803 桌面）
A16_TIME_COEF = 1.0 - 1.0 / UNLOCK_FACTOR   # 0.3842
DEFAULT_BASE = 963.0    # 我们的 37,468-token 基线 prefill tok/s
NON_GEMM_DEFAULT = 0.15 # 不可加速占比（attention/KV 写入/softmax/GDN/调度）


def fix_stdout():
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass


def port_busy(host, port):
    s = socket.socket()
    s.settimeout(0.5)
    try:
        s.connect((host, port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def wait_port(host, port, timeout):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if port_busy(host, port):
            return True
        time.sleep(0.5)
    return False


def sse_once(host, port, model_id, prompt, max_tokens, timeout):
    '''发一个流式请求，返回 (ttft_s, total_s, usage_dict, text_len)。'''
    url = 'http://%s:%d/v1/chat/completions' % (host, port)
    body = {'model': model_id,
            'messages': [{'role': 'user', 'content': prompt}],
            'max_tokens': max_tokens,
            'temperature': 0,
            'stream': True,
            'stream_options': {'include_usage': True}}
    req = urllib.request.Request(url, data=json.dumps(body).encode('utf-8'),
                                 headers={'Content-Type': 'application/json'})
    t0 = time.time()
    ttft = None
    total = None
    usage = {}
    nchars = 0
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        for raw in resp:
            now = time.time() - t0
            line = raw.decode('utf-8', 'replace').strip()
            if not line.startswith('data:'):
                continue
            data = line[5:].strip()
            if data == '[DONE]':
                total = now
                break
            try:
                obj = json.loads(data)
            except Exception:
                continue
            if obj.get('usage'):
                usage = obj['usage']
            choices = obj.get('choices') or []
            if choices:
                delta = choices[0].get('delta') or {}
                txt = delta.get('content') or ''
                if txt and ttft is None:
                    ttft = now
                nchars += len(txt)
            total = now
    if ttft is None:
        ttft = total if total is not None else time.time() - t0
    if total is None:
        total = ttft
    return ttft, total, usage, nchars


def run_arm(tag, args, host, port, extra_flag, prompt, log_path, started_here):
    '''跑一臂；若 started_here 则自己起引擎并在结束时只杀自己起的那个进程。'''
    proc = None
    logf = None
    try:
        if started_here:
            argv = [args.exe, args.model,
                    '--host', host,
                    '--port', str(port),
                    '--max-context', str(args.max_context),
                    '--model-id', args.api_model]
            if extra_flag:
                argv.append(extra_flag)
            if args.extra_args:
                argv.extend(args.extra_args.split())
            logf = open(log_path, 'w', encoding='utf-8', errors='replace')
            print('[%s] spawn: %s' % (tag, ' '.join(argv)))
            proc = subprocess.Popen(argv, stdout=logf, stderr=subprocess.STDOUT)
            if not wait_port(host, port, args.ready_timeout):
                raise RuntimeError('[%s] 引擎 %ds 内没监听 %s:%d（看 %s）'
                                   % (tag, args.ready_timeout, host, port, log_path))
            time.sleep(args.settle)
        else:
            if not port_busy(host, port):
                raise RuntimeError('[%s] --no-start 但 %s:%d 没在监听' % (tag, host, port))
        print('[%s] 发请求（prompt %d 字符，max_tokens=%d）...' % (tag, len(prompt), args.max_tokens))
        ttft, total, usage, nchars = sse_once(host, port, args.api_model, prompt,
                                              args.max_tokens, args.timeout)
        ptoks = (usage or {}).get('prompt_tokens')
        ctoks = (usage or {}).get('completion_tokens')
        if not ptoks:
            ptoks = max(1, int(round(len(prompt) / args.chars_per_token)))
            print('[%s] 警告：响应无 prompt_tokens，按 %.2f 字符/token 估得 %d'
                  % (tag, args.chars_per_token, ptoks))
        per_tok = ttft / float(ptoks)
        speed = float(ptoks) / ttft if ttft > 0 else 0.0
        print('[%s] ttft=%.3fs total=%.3fs prompt_tokens=%s speed=%.1f tok/s per_tok=%.6f s'
              % (tag, ttft, total, ptoks, speed, per_tok))
        return {'tag': tag, 'flag': extra_flag or '(default)', 'ttft_s': ttft,
                'total_s': total, 'prompt_tokens': ptoks, 'completion_tokens': ctoks,
                'prefill_tok_s': speed, 's_per_token': per_tok,
                'usage': usage, 'log': log_path if started_here else None}
    finally:
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=30)
            except Exception:
                proc.kill()
            print('[%s] 已停掉本脚本自己起的引擎 pid=%d' % (tag, proc.pid))
        if logf is not None:
            logf.close()


def solve(arm_a, arm_b, non_gemm):
    '''由两臂的每-token prefill 时间反解 f、f_eff、S 与预测值。'''
    ta = arm_a['s_per_token']
    tb = arm_b['s_per_token']
    base = arm_a['prefill_tok_s']
    r = tb / ta if ta > 0 else float('nan')
    q = (r - 1.0) / R_INT8_VS_A16
    f = 1.0 - q
    f_clip = min(1.0, max(0.0, f))
    f_eff = max(0.0, f_clip - non_gemm)
    s_lead = 1.0 / (1.0 - A16_TIME_COEF * f_clip)
    s_cons = 1.0 / (1.0 - A16_TIME_COEF * f_eff)
    return {'ratio_tb_ta': r, 'int8_time_share_q': q, 'f': f, 'f_clip': f_clip,
            'f_eff': f_eff, 'non_gemm_share': non_gemm,
            'S_lead': s_lead, 'S_cons': s_cons,
            'base_speed': base,
            'pred_speed_lead': base * s_lead, 'pred_speed_cons': base * s_cons,
            'pred_ttft_lead_s': arm_a['ttft_s'] / s_lead,
            'pred_ttft_cons_s': arm_a['ttft_s'] / s_cons}


def verdict(sol):
    f = sol['f_clip']
    r = sol['ratio_tb_ta']
    if r > 1.77:
        return ('NO-GO', 'B 慢了 1.77 倍以上（q>1，模型外）：先看引擎日志，多半是参考 rung 或别的东西在起作用');
    if sol['ratio_tb_ta'] < 1.0:
        return ('NO-GO', 'B 组反而更快 => 读反了或 flags 没传对，数据不可用');
    if f >= 0.60:
        return ('GO', 'A16 占 prefill 时间 >=60%，解锁预期实打实；仍需先做只回放 dry-run 与 ssdiag 基线');
    if f >= 0.45:
        return ('边缘', 'A16 占 45~60%：收益在中低区间，优先做软件侧调参与前缀缓存');
    return ('NO-GO', 'A16 占比 <45%：解锁收益被 int8 通路吃掉，不值得过固件事务');


def caveat(sol):
    if abs(sol['ratio_tb_ta'] - 1.0) < 0.02:
        return ('两臂几乎同速：GO 的前提是「int8 真的没参与」；也可能是 --no-prefill-a8 没生效，'
                '或我们本来就在参考 rung 上。先看引擎日志确认开关生效，再相信 f=1。')
    return ''


def table(base):
    '''A 基线固定时，B 组读数 -> f / S 的对照表。'''
    rows = []
    for b in (963, 900, 850, 800, 750, 700, 650, 600, 550, 500):
        r = base / float(b)
        q = (r - 1.0) / R_INT8_VS_A16
        f = min(1.0, max(0.0, 1.0 - q))
        f_eff = max(0.0, f - NON_GEMM_DEFAULT)
        s_lead = 1.0 / (1.0 - A16_TIME_COEF * f)
        s_cons = 1.0 / (1.0 - A16_TIME_COEF * f_eff)
        rows.append({'B': b, 'f': f, 'S_lead': s_lead, 'S_cons': s_cons,
                     'pred_lead': base * s_lead, 'pred_cons': base * s_cons,
                     'v': verdict({'f_clip': f, 'ratio_tb_ta': r})[0]})
    return rows


def print_table(base):
    print('');
    print('读表（A 基线 %.0f tok/s；f=1-q，q=(T_B/T_A-1)/0.87）：' % base);
    print('  B组tok/s |   f    | f_eff  |  S(lead) | 预估tok/s(lead) | S(保守) | 预估tok/s(保守) | 判定');
    for row in table(base):
        print('  %8d | %5.3f | %5.3f | %7.3f | %14.0f | %6.3f | %14.0f | %s'
              % (row['B'], row['f'], max(0.0, row['f'] - NON_GEMM_DEFAULT),
                 row['S_lead'], row['pred_lead'], row['S_cons'], row['pred_cons'], row['v']))
    print('  说明：f_eff = f - %.2f（扣掉不可加速的 attention/KV/调度占比）' % NON_GEMM_DEFAULT);
    print('  GO 线：f>=0.60 等价于 B>=%d tok/s（A=%.0f 时）' % (int(base / 1.348), base));


def selftest():
    ok = True
    def check(name, got, want, tol=1e-3):
        nonlocal ok
        good = abs(got - want) <= tol
        ok = ok and good
        print(('  PASS ' if good else '  FAIL ') + name + ' got=%.6f want=%.6f' % (got, want))
    print('SELFTEST（不连引擎、不占卡）');
    a = {'s_per_token': 39.0 / 37468.0, 'prefill_tok_s': 37468.0 / 39.0, 'ttft_s': 39.0}
    # 构造：B 慢 30% => q=0.30/0.87
    b = {'s_per_token': a['s_per_token'] * 1.30, 'prefill_tok_s': a['prefill_tok_s'] / 1.30, 'ttft_s': 39.0 * 1.30}
    sol = solve(a, b, 0.15)
    check('q', sol['int8_time_share_q'], 0.30 / 0.87)
    check('f', sol['f'], 1.0 - 0.30 / 0.87)
    check('S_lead(f=0.6552)', sol['S_lead'], 1.0 / (1.0 - 0.3842 * 0.655172))
    check('f_eff', sol['f_eff'], 1.0 - 0.30 / 0.87 - 0.15)
    check('S_cons', sol['S_cons'], 1.0 / (1.0 - 0.3842 * (1.0 - 0.30 / 0.87 - 0.15)))
    v = verdict(sol)
    print('  verdict(r=1.30) = %s' % v[0]);
    ok = ok and v[0] == 'GO'
    # 方向性：B 越慢 -> f 越小 -> S 越小
    prev_f = 2.0
    for mult in (1.0, 1.2, 1.4, 1.6, 1.8):
        bb = {'s_per_token': a['s_per_token'] * mult, 'prefill_tok_s': a['prefill_tok_s'] / mult, 'ttft_s': 39.0 * mult}
        s = solve(a, bb, 0.15)
        mono = s['f'] < prev_f + 1e-12
        ok = ok and mono
        prev_f = s['f']
        print('  monotone mult=%.1f f=%.4f S_lead=%.4f %s' % (mult, s['f'], s['S_lead'], 'PASS' if mono else 'FAIL'))
    # 边界：B 与 A 同速
    same = solve(a, dict(a), 0.15)
    ok = ok and verdict(same)[0] == 'GO'
    ok = ok and len(caveat(same)) > 0
    check('f(B==A)', same['f'], 1.0)
    check('S(B==A)', same['S_lead'], 1.0 / (1.0 - 0.3842))
    # 表内关键值
    rows = {r['B']: r for r in table(963.0)}
    check('table[800].f', rows[800]['f'], 1.0 - ((963.0 / 800.0) - 1.0) / 0.87)
    ok = ok and rows[963]['v'] == 'GO' and rows[600]['v'] == 'NO-GO'
    print('  GO 线反查：f>=0.6 <=> B>=%d' % int(963 / 1.348))
    print_table(963.0)
    print('SELFTEST ' + ('PASS' if ok else 'FAIL'))
    return 0 if ok else 1


BANNER = (
    '[历史工具] 2026-10-30 实测 --no-prefill-a8：8k 1.10k->396.7 tok/s、24k 1.03k->386.2',
    '（T_B/T_A = 2.66~2.77），超出本脚本 f 反解模型的定义域（最大 1.87）=> f 不可辨识。',
    '解锁上限改按 A16 时间占比算：1/(0.636 + 0.364/1.624) = 1.163x（+16.3%）。结论以',
    'reports/解锁-研究-nvUEFI.md §7.2 为准；本脚本仅作复现与历史留档，不再用于出结论。',
)

def main():
    ap = argparse.ArgumentParser(description='解锁定价 A/B（默认 vs --no-prefill-a8）')
    ap.add_argument('--exe', help='引擎 exe，如 engine/ninfer-serve-89.exe')
    ap.add_argument('--model', help='模型文件 .ninfer')
    ap.add_argument('--prompt-file', help='37K 提示词文本（utf-8）')
    ap.add_argument('--port', type=int, default=18080, help='本脚本自己的端口（默认 18080；被占即退出）')
    ap.add_argument('--host', default='127.0.0.1')
    ap.add_argument('--max-context', type=int, default=40960)
    ap.add_argument('--max-tokens', type=int, default=8, help='只测首字，输出给很小')
    ap.add_argument('--ab-flag', default='--no-prefill-a8')
    ap.add_argument('--extra-args', default='', help='两臂共用的额外引擎参数，如 "--spec mtp --prefill-chunk 2048"')
    ap.add_argument('--api-model', default='pricing-ab')
    ap.add_argument('--chars-per-token', type=float, default=3.2)
    ap.add_argument('--non-gemm-share', type=float, default=NON_GEMM_DEFAULT,
                    help='不可加速占比（默认 0.15，出自 1k/37k/200k 三点拟合）')
    ap.add_argument('--ready-timeout', type=int, default=240)
    ap.add_argument('--settle', type=float, default=2.0)
    ap.add_argument('--timeout', type=int, default=900)
    ap.add_argument('--out', default='', help='结果 JSON 路径（默认 logs/unlock_pricing_<ts>.json）')
    ap.add_argument('--dry-run', action='store_true', help='只打印两臂命令，不执行')
    ap.add_argument('--selftest', action='store_true', help='空跑自检（不连引擎）')
    ap.add_argument('--yes', action='store_true', help='跳过端口占用确认')
    args = ap.parse_args()
    fix_stdout()
    print('\n'.join(BANNER))
    if args.selftest:
        return selftest()
    missing = [n for n in ('exe', 'model', 'prompt_file') if not getattr(args, n)]
    if missing:
        ap.error('缺少参数: --' + ', --'.join(m.replace('_', '-') for m in missing))
    prompt = '' if args.dry_run else open(args.prompt_file, 'r', encoding='utf-8').read()
    if port_busy(args.host, args.port):
        print('端口 %d 已被占用（可能是别人的服务）。换 --port，或确认后加 --yes 复用。' % args.port)
        if not args.yes:
            return 2
    reuse = port_busy(args.host, args.port)
    ts = time.strftime('%Y%m%d_%H%M%S')
    out = args.out or os.path.join('logs', 'unlock_pricing_%s.json' % ts)
    os.makedirs(os.path.dirname(out) or '.', exist_ok=True)
    log_a = os.path.join(os.path.dirname(out) or '.', 'unlock_pricing_%s_A.log' % ts)
    log_b = os.path.join(os.path.dirname(out) or '.', 'unlock_pricing_%s_B.log' % ts)
    if args.dry_run:
        base = [args.exe, args.model, '--host', args.host, '--port', str(args.port),
                '--max-context', str(args.max_context), '--model-id', args.api_model]
        print('A: ' + ' '.join(base + (args.extra_args.split() if args.extra_args else [])));
        print('B: ' + ' '.join(base + [args.ab_flag] + (args.extra_args.split() if args.extra_args else [])));
        print('请求：POST http://%s:%d/v1/chat/completions  stream=true  max_tokens=%d'
              % (args.host, args.port, args.max_tokens));
        print('（dry-run 未执行任何东西）')
        return 0
    print('== A 臂：默认 ==')
    arm_a = run_arm('A', args, args.host, args.port, '', prompt, log_a, not reuse)
    print('== B 臂：%s ==' % args.ab_flag)
    arm_b = run_arm('B', args, args.host, args.port, args.ab_flag, prompt, log_b, not reuse)
    sol = solve(arm_a, arm_b, args.non_gemm_share)
    v, why = verdict(sol)
    print('');
    print('== 结论 ==')
    print('  A: %.1f tok/s, ttft %.2fs, prompt_tokens %s' % (arm_a['prefill_tok_s'], arm_a['ttft_s'], arm_a['prompt_tokens']))
    print('  B: %.1f tok/s, ttft %.2fs  (B/A 时间比 %.4f)' % (arm_b['prefill_tok_s'], arm_b['ttft_s'], sol['ratio_tb_ta']))
    print('  int8 时间占比 q=%.4f  =>  f(A16 占比)=%.4f  f_eff(扣 %.2f)=%.4f'
          % (sol['int8_time_share_q'], sol['f_clip'], sol['non_gemm_share'], sol['f_eff']))
    print('  解锁预期：S=%.3f（口径按 lead 的 f） -> prefill %.0f tok/s, TTFT %.1fs'
          % (sol['S_lead'], sol['pred_speed_lead'], sol['pred_ttft_lead_s']))
    print('  保守口径：S=%.3f -> prefill %.0f tok/s, TTFT %.1fs'
          % (sol['S_cons'], sol['pred_speed_cons'], sol['pred_ttft_cons_s']))
    print('  判定：%s —— %s' % (v, why))
    cv = caveat(sol)
    if cv:
        print('  ! 提醒：%s' % cv)
    print_table(arm_a['prefill_tok_s'])
    payload = {'ts': ts, 'args': vars(args), 'arm_a': arm_a, 'arm_b': arm_b,
               'solution': sol, 'verdict': v, 'why': why, 'table': table(arm_a['prefill_tok_s'])}
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print('结果已写：%s' % out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
