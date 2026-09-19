import unittest
import numpy as np
from realtime.pca_experiment import PCAStream, features, group_features


class PCATests(unittest.TestCase):
    def test_residual_reduction_requires_two_windows_and_has_no_root_pid(self):
        stream=self.make_stream()
        stream.models[0]['residual_low']=.5
        stream.reset()
        stream.consume({'type':'wafer_start','wafer':25,'total_devices':80})
        for batch in range(1,6):
            keys=[f'{batch}:{i}' for i in range(4)]
            stream.consume({'type':'test_start','batch':batch,'devices':[{'key':k} for k in keys]})
            amplitude=10. if batch<=2 else .1
            stream.consume({'type':'measurement','indices':[0,1],'keys':keys,
                            'values':[[0.,amplitude*(-1)**i] for i in range(4)],'stage':'stage0'})
            if batch<5:self.assertNotIn('0:residual_spread_low',stream.alerts)
            if batch<5:
                stream.consume({'type':'test_end','outcomes':[{'key':k,'pid':k} for k in keys]})
        alert=stream.alerts['0:residual_spread_low']
        self.assertEqual(alert['batch'],5)
        self.assertEqual(alert['suspect_keys'],[])
        self.assertEqual(len(alert['window_keys']),16)
        self.assertEqual(alert['potential_unstarted_devices'],60)
        self.assertIn('residual_evidence',alert)

    def test_temporal_features_ignore_constant_offset_but_detect_change(self):
        block = np.tile(np.array([[-1.,1.],[1.,-1.]]),(8,1))
        original = group_features(block, np.ones(2), True)
        np.testing.assert_allclose(original, group_features(block+100, np.ones(2), True))
        shifted=block.copy(); shifted[8:]+=10
        self.assertGreater(group_features(shifted,np.ones(2),True)[0], original[0])
        reduced=block.copy(); reduced[8:]*=.1
        self.assertLess(group_features(reduced,np.ones(2),True)[1], .02)

    def test_autoencoder_saved_weights_match_predict(self):
        from sklearn.neural_network import MLPRegressor
        rng=np.random.default_rng(42); x=rng.normal(size=(40,3))
        net=MLPRegressor(hidden_layer_sizes=(2,),activation='tanh',solver='lbfgs',
                         max_iter=2000,random_state=42).fit(x,x)
        model=dict(center=np.zeros(3),scale=np.ones(3),encoder=net.coefs_[0],
                   encoder_bias=net.intercepts_[0],decoder=net.coefs_[1],decoder_bias=net.intercepts_[1],
                   latent_center=np.zeros(2),variance=np.ones(2))
        q,_,_,residual=features(x,model)
        np.testing.assert_allclose(x-residual,net.predict(x),atol=1e-10)
        np.testing.assert_allclose(q,np.mean((x-net.predict(x))**2,axis=1))

    def make_stream(self):
        m = dict(indices=np.array([0,1]), center=np.zeros(2), scale=np.ones(2),
                 components=np.array([[1.,0.]]), variance=np.ones(1),
                 die_limits=np.ones(2), group_high=np.ones(2)*100, group_low=1e-6)
        stream = PCAStream(['earlier','current'], [m])
        stream.consume({'type':'wafer_start','wafer':'14','total_devices':80})
        stream.consume({'type':'test_start','batch':1,'devices':[{'key':str(i)} for i in range(4)]})
        return stream

    def event(self):
        return {'type':'measurement','indices':[0,1], 'keys':[str(i) for i in range(4)],
                'values':[[0.,10.]]*4,'stage':'stage0'}

    def test_residual_score_and_latent_score_are_distinct(self):
        stream = self.make_stream()
        q,t,_,residual = features(np.array([[0.,10.],[10.,0.]]), stream.models[0])
        np.testing.assert_allclose(q, [50.,0.])
        np.testing.assert_allclose(t, [0.,100.])
        np.testing.assert_allclose(residual[0], [0.,10.])

    def test_pid_and_coordinates_not_backfilled_into_old_frames(self):
        stream = self.make_stream()
        stream.consume(self.event())
        self.assertFalse(stream.alerts)  # Four high-score dies alone are insufficient.
        stream.consume({'type':'test_end','outcomes':[{'key':str(i),'pid':100+i,'x':i,'y':0} for i in range(4)]})
        self.assertIsNone(stream.frames[0]['ranking'][0]['pid'])
        self.assertEqual(stream.frames[0]['map'], [])
        self.assertEqual(stream.frames[-1]['ranking'][0]['pid'], 100)

    def test_future_stage_repeated_results_and_w2_rejected(self):
        stream = self.make_stream()
        bad = self.event(); bad['indices']=[0,1,2]
        with self.assertRaises(ValueError): stream.consume(bad)
        stream.consume(self.event())
        with self.assertRaises(ValueError): stream.consume(self.event())
        with self.assertRaises(ValueError): stream.consume({'type':'wafer_start','wafer':2,'total_devices':80})


if __name__=='__main__': unittest.main()
