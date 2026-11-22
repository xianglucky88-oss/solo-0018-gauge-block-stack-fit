from gauge.search import recommend as conforming_stacks
from gauge.search import available as certificate_status
from gauge.fit import check as stack_interval
from gauge.period_check import check as period_check
from gauge.certificate_ledger import ledger as certificate_ledger
from gauge.availability_windows import windows as availability_windows
from gauge.witness import inspect as witness
from gauge.stack_delta import compare as stack_delta
from gauge.change_chain import check as change_chain
from gauge.certificate_drift import reconcile as certificate_drift

PRODUCT = '0018-gauge-block-stack-fit'
TITLE = '量块组合公差工作台'
WORK_LABEL = '计量记录 / 证书日期'
THEME = 'metrology'
DEFAULT_DATASET = 'stackfit-set'
PORT = 8818

OPERATIONS = {
    'conforming-stacks': ('合规组块', conforming_stacks),
    'certificate-status': ('证书有效性', certificate_status),
    'stack-interval': ('指定组合公差', stack_interval),
    'period-check': ('跨日组合复验', period_check),
    'certificate-ledger': ('固定组合证书账', certificate_ledger),
    'availability-windows': ('证书有效期分段', availability_windows),
    'witness': ('组块实测见证核验', witness),
    'stack-delta': ('同日组块差值', stack_delta),
    'change-chain': ('同日换型链核验', change_chain),
    'certificate-drift': ('换证差值与复测核对', certificate_drift),
}
def _review_eligible(report):
    return report['accepted']


REVIEW = ('witness', _review_eligible)
REQUIRED = ('conforming-stacks', 'certificate-status', 'stack-interval')
