#!/usr/bin/env python3
"""VM 主集群入口；历史本地 kind 批次只允许恢复，不再续跑。"""
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'phase02'))
import runtime as r
import cli


def driver(argv):
    records=Path(argv[argv.index('--records')+1])
    mode=argv[argv.index('--mode')+1]
    context=records/'context.json'
    if context.exists() and json.loads(context.read_text()).get('isolation'):
        r.require(mode in ['recover','cleanup'],'旧 Mac/kind 批次已停用，只允许原批清理；VM 实验必须使用新目录。')
        return r.module('legacy_dataplane_cleanup',Path(__file__).with_name('legacy_kind.py'))
    return r.module('vm_dataplane',Path(__file__).with_name('vm.py'))


if __name__=='__main__':
    try:
        cli.run(driver(sys.argv))
    except (ValueError,KeyError,OSError) as error:
        sys.exit(str(error))
