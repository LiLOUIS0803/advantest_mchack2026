import time
from .data import read_wafer, stage_indices


def events(entry):
    columns, rows, x = read_wafer(entry)
    stages = stage_indices(columns)
    yield {'type':'wafer_start','wafer':entry['wafer'],'lot':rows[0][1], 'total_devices':len(rows),'mode':'replay'}
    for start in range(0,len(rows),4):
        batch = start//4+1
        part = rows[start:start+4]
        if len({r[3] for r in part}) != len(part):
            raise ValueError('Replay assumes four consecutive rows form a multisite batch')
        keys = [f'{entry["wafer"]}:{batch}:{r[3]}' for r in part]
        yield {'type':'test_start','batch':batch,'devices':[{'key':k,'site':int(r[3])} for k,r in zip(keys,part)]}
        for stage, indices in enumerate(stages):
            yield {'type':'measurement','keys':keys,'indices':indices.tolist(),
                   'values':x[start:start+len(part),indices].tolist(),
                   'stage':'前段／IDDQ' if stage==0 else f'sensor{stage} + subflow{stage}'}
        # CSV coordinates are final records: reveal them conservatively at TestEnd.
        yield {'type':'test_end','outcomes':[{'key':k,'pid':r[0],'passed':int(r[6])==0,
                                            'x':int(r[4]),'y':int(r[5]), 'pf':int(r[6]),
                                            'sbin':int(r[7]),'hbin':int(r[8])} for k,r in zip(keys,part)]}
    yield {'type':'wafer_end'}


def apply_event(engine,event):
    start = time.perf_counter()
    kind = event['type']
    if kind == 'wafer_start':
        engine.reset(event['wafer'],event.get('lot',''),event.get('total_devices'),event.get('mode','live'))
    elif kind == 'test_start':
        engine.start_batch(event['batch'],event['devices'])
    elif kind == 'measurement':
        indices = event.get('indices')
        if indices is None:
            indices = [engine.lookup[name] for name in event['tests']]
        engine.measurement(event['keys'],indices,event['values'],event.get('stage','測項結果'))
    elif kind == 'test_end':
        engine.finish_batch(event['outcomes'])
    elif kind == 'wafer_end':
        if engine.current:
            raise ValueError('Cannot end wafer with unfinished batch')
        engine.ended = True
    else:
        raise ValueError(f'Unsupported event: {kind}')
    engine.latency_ms = round((time.perf_counter()-start)*1000,3)
