"""Audit C01 attachments against an independently captured author snapshot; offline."""
import argparse
import json
from pathlib import Path
import sys

from autoresearch.c01 import C01Error
from autoresearch.c01_source_audit import audit_sources
from autoresearch.contracts import ResearchError


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', required=True)
    parser.add_argument('--snapshot', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    try:
        result = audit_sources(args.archive, args.snapshot)
        output = Path(args.output)
        output.mkdir(parents=True, exist_ok=False)
        (output / 'source-audit.json').write_text(json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2), encoding='utf-8')
        lines = ['# C01原始来源字节核验', '', '作者发布附件与队员原包逐字节比较；不执行公式或拟合。', '',
                 '| 附件 | 原包字节 | 上游字节 | 完全相同 |', '|---|---:|---:|---|']
        lines += [f"| {row['name']} | {row['archive_bytes']} | {row['upstream_bytes']} | {row['byte_equal']} |" for row in result['files']]
        lines += ['', '许可是当前源页面人工核对记录；来源清单不是数字签名。文件一致不能证明科学定义正确、样本独立或满足外验条件。',
                  '完整SHA、来源链接、原始单元格/公式和剩余边界在source-audit.json中。样本数保持8，没有新增训练或云/模型调用。', '']
        (output / 'README.md').write_text('\n'.join(lines), encoding='utf-8')
        print(json.dumps({'ok': result['all_five_attachments_byte_equal'], 'output': str(output.absolute()),
                          'result': result}, ensure_ascii=False, indent=2))
        return 0 if result['all_five_attachments_byte_equal'] else 1
    except (ResearchError, C01Error, ValueError, OSError) as error:
        print(json.dumps({'ok': False, 'error': {'code': getattr(error, 'code', 'SOURCE_UNAVAILABLE'),
              'message': str(error) if isinstance(error, (ResearchError, C01Error)) else 'Source snapshot or output is unavailable.'}}, ensure_ascii=False))
        return 1


if __name__ == '__main__': raise SystemExit(main())
