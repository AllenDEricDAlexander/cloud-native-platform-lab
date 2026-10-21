# ${{ values.name }}

语言：${{ values.language }}；CI：${{ values.ci }}；责任组：${{ values.owner }}。

服务使用/health、/ready、/version、/compute、/metrics。发布后核对实际Digest与source revision。

数据依赖：${{ values.dataService }}。应用回退保留数据库结构；删除资源须备份与独立审批。
