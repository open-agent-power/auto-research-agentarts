"""Small, deterministic SVG over published per-group diagnostic arithmetic."""
import math
from xml.sax.saxutils import escape


POLICIES = {
    'positive_equal_batch': '正计数 · 批次等权',
    'positive_equal_section': '正计数 · 分区等权',
    'recorded_equal_batch': '保留零 · 批次等权',
    'recorded_equal_section': '保留零 · 分区等权',
}


def render_diagnostic(view):
    rows = view['topography_chart']
    if not rows:
        raise ValueError('No executed topography result to plot')
    indexed = {}
    for row in rows:
        key = (row['policy'], row['topography'])
        if (key in indexed or key[0] not in POLICIES or type(key[1]) is not int
                or not 2 <= key[1] <= 36 or type(row['n']) is not int or row['n'] <= 0
                or any(type(row[k]) not in (int, float) or not math.isfinite(row[k]) for k in ('mae', 'delta_mae_vs_chemistry'))):
            raise ValueError('Invalid diagnostic chart row')
        indexed[key] = row
    if set(indexed) != {(p, t) for p in POLICIES for t in range(2, 37)}:
        raise ValueError('All 35 observed topographies under four policies are required')
    scale = max(abs(r['delta_mae_vs_chemistry']) for r in rows) or 1
    out = ['<svg xmlns="http://www.w3.org/2000/svg" width="1100" height="400" viewBox="0 0 1100 400" role="img" aria-labelledby="title desc">',
           '<title id="title">当前候选相对化学基线：35个纹理组的误差变化</title>',
           '<desc id="desc">每格为一个纹理组。绿色误差更低，橙色误差更高，白色相同。四规则使用同一色阶。悬停格子可读准确值。没有计算显著性检验。</desc>',
           '<rect width="1100" height="400" rx="16" fill="#fbfcfb"/>',
           '<g font-family="Microsoft YaHei, Noto Sans CJK SC, sans-serif" fill="#233c35">',
           '<text x="28" y="39" font-size="22" font-weight="600">误差增加发生在哪些纹理组？</text>',
           '<text x="28" y="67" font-size="14">α=0.5 − 化学基线的 MAE；同规则内比较，负值更好。每格来自已保存预测。</text>']
    for t in range(2, 37):
        out.append(f'<text x="{174+(t-2)*22}" y="103" text-anchor="middle" font-size="11">{t}</text>')
    out.append('<text x="28" y="103" font-size="12">纹理编号</text>')
    for i, (policy, label) in enumerate(POLICIES.items()):
        y = 118+i*48
        data = [indexed[(policy, t)] for t in range(2, 37)]
        better = sum(r['delta_mae_vs_chemistry'] < -1e-12 for r in data)
        worse = sum(r['delta_mae_vs_chemistry'] > 1e-12 for r in data)
        out.append(f'<text x="28" y="{y+21}" font-size="13">{escape(label)}</text>')
        for row in data:
            value = row['delta_mae_vs_chemistry']; strength = min(1, abs(value)/scale)
            target = (182, 94, 45) if value > 0 else (43, 123, 96)
            color = '#'+''.join(f'{round(247+(c-247)*strength):02x}' for c in target)
            tooltip = f"纹理 {row['topography']}；n={row['n']}；MAE={row['mae']:.6f}；ΔMAE={value:+.6f}"
            out.append(f'<rect x="{164+(row["topography"]-2)*22}" y="{y}" width="20" height="30" rx="3" fill="{color}" stroke="#d7dfda" stroke-width="0.5"><title>{escape(tooltip)}</title></rect>')
        out.append(f'<text x="948" y="{y+21}" font-size="13">{worse} 更差 / {better} 改善</text>')
    for x, color, label in [(28, '#2b7b60', f'−{scale:.3f}'), (160, '#f7f7f7', '0'), (242, '#b65e2d', f'+{scale:.3f}')]:
        out.append(f'<rect x="{x}" y="330" width="20" height="14" fill="{color}" stroke="#d7dfda"/><text x="{x+28}" y="342" font-size="12">{label}</text>')
    out.append('<text x="28" y="378" font-size="13">描述已有误差分布；不证明纹理因果作用或统计显著性。原始红通道代理尚未确认为 ALP。</text></g></svg>')
    return ''.join(out).encode('utf-8')
