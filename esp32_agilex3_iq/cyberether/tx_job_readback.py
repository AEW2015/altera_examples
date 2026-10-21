"""Strict received TX_ON identity/settings check, independent of requested data."""


def validate_tx_on(text,config,*,channel,backoff_qdb,limit_ms=500):
    parts=text.split(',')
    if parts[0]!='TX_ON':raise ValueError('Expected TX_ON readback')
    actual={}
    try:
        for part in parts[1:]:
            name,value=part.split('=',1)
            if name in actual:raise ValueError('Duplicate TX_ON field')
            actual[name]=int(value)
    except (TypeError,ValueError) as error:
        raise ValueError('Malformed TX_ON readback') from error
    expected=dict(id=config['job'],channel=channel,backoff_qdb=backoff_qdb,limit_ms=limit_ms)
    if actual!=expected:raise ValueError(f'TX_ON identity/settings mismatch: actual={actual}, expected={expected}')
    return dict(actual,line=text,scope='Actual received transmitter job/channel/backoff/duration acknowledgement; attenuation code is not calibrated RF output power')
