import contextlib,copy,importlib.util,json,sqlite3,sys,tempfile,time,types,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from stock101.crypto import telegram_view as view,execution_strategies as rules,service
from stock101.crypto.multi import MultiEngine
from stock101.crypto.live import LiveEngine
from test_execution_strategies import RuleMarket
from test_live import Broker,FX
import stock101_telegram as commands

def state():
 return dict(mode='paper',running=True,reason=None,equity='121.21',cash='90',capital='100',realized='10.1',unrealized='11.11',
  marked_at=time.time(),completed_at=time.time(),last_assessment_at=time.time(),last_product='BTC-USD',last_reason='STRATEGY_HOLD',
  positions=[],fills=[],fill_count=0,now=time.time())

class ViewTests(unittest.TestCase):
 def test_every_screen_is_bounded_and_buttons_are_read_only(self):
  for mode in view.MODES:
   for page in view.VIEWS:
    s=state();s['mode']=mode;r=view.render(s,page)
    self.assertLess(len(r['text'].encode('utf-16-le'))//2,3400);self.assertTrue(r['protect_content'])
    for row in r['reply_markup']['inline_keyboard']:
     for b in row:
      self.assertRegex(b['callback_data'],r'^st101:(paper|live):(status|positions|fills|strategies)$')
      self.assertLessEqual(len(b['callback_data'].encode()),64)
 def test_snapshot_is_read_only_and_never_calls_market_or_orders(self):
  with tempfile.TemporaryDirectory() as tmp:
   m=RuleMarket();e=MultiEngine(Path(tmp)/'p.db',m,strategy_version=rules.VERSION)
   with e.repo.db() as c:
    c.execute("INSERT INTO paper_accounts VALUES('CAD','100','100') ON CONFLICT(currency) DO NOTHING")
    e.repo.put(c,'portfolio_snapshots','mark',dict(equity='100',cash='100',unrealized='0',positions=[]))
    before=list(c.iterdump())
   with patch.object(m,'get_orderbook',side_effect=AssertionError('market called')):
    r=view.response(e,'paper');self.assertIn('100.00 CAD',r['text']);self.assertIn('모의매매',r['text'])
   with e.repo.db() as c:self.assertEqual(list(c.iterdump()),before)
 def test_live_offline_view_does_not_check_credentials_or_activate(self):
  with tempfile.TemporaryDirectory() as tmp:
   m=RuleMarket();br=Broker(m);e=LiveEngine(Path(tmp)/'live.db',br,m,FX(),strategy_version=rules.VERSION)
   with patch.object(br,'permissions',side_effect=AssertionError('credentials called')):
    r=view.response(e,'live');self.assertIn('비활성',r['text']);self.assertIn('예산 한도는 Coinbase 잔액이 아닙니다',r['text'])
   self.assertFalse(e.enabled());self.assertEqual(br.sent,[])
 def test_financial_values_are_distinct_and_stale_is_visible(self):
  s=state();s['marked_at']=time.time()-900;s['running']=False;s['reason']='SECRET_should_not_leak'
  text=view.render(s)['text'];self.assertIn('확정 손익: 10.10 CAD',text);self.assertIn('평가 손익: 11.11 CAD',text)
  self.assertIn('누적 가상 입금: 100.00 CAD',text);self.assertIn('최신 평가액을 확인하지 못했습니다',text);self.assertNotIn('SECRET',text)
 def test_trade_shows_fee_inclusive_debit_and_net_credit(self):
  s=state();s['fills']=[dict(product='BTC-USD',side=side,notional='10',fee='.1',created=time.time(),currency='CAD',strategy_id='dca_weekly') for side in ('BUY','SELL')]
  text=view.render(s,'fills')['text'];self.assertIn('총 지출 10.10 CAD',text);self.assertIn('순 수령 9.90 CAD',text)
 def test_invalid_mode_or_view_never_reads_ledger(self):
  e=Mock()
  for mode,page in [('../../data','status'),('paper','buy'),('live','start')]:
   with self.assertRaises(ValueError):view.response(e,mode,page)
  e.repo.db.assert_not_called()
 def test_service_route_uses_existing_engine_without_action(self):
  e=Mock()
  with patch.object(service,'engine',return_value=e),patch.object(view,'response',return_value={'text':'safe'}) as render,patch.object(service,'live_engine') as live:
   self.assertEqual(service.get(None,'telegram',dict(mode='paper',view='fills')),{'text':'safe'})
   render.assert_called_once_with(e,'paper','fills');live.assert_not_called()

class FakeApp:
 def __init__(self,path):self.DATA=Path(path);self.local_learning=types.SimpleNamespace(touch=lambda:None)
 @contextlib.contextmanager
 def db(self):
  c=sqlite3.connect(self.DATA/'airi.db');c.row_factory=sqlite3.Row
  try:yield c;c.commit()
  finally:c.close()
 def rows(self,sql,args=()):
  with self.db() as c:return [dict(r) for r in c.execute(sql,args)]

class OwnerRoutingTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.app=FakeApp(self.tmp.name)
  spec=importlib.util.spec_from_file_location('stock_bridge_test',Path(__file__).parents[1]/'telegram_bridge.py')
  self.bridge=importlib.util.module_from_spec(spec)
  with patch.dict(sys.modules,{'video_telegram':types.SimpleNamespace(),'telegram_news':types.SimpleNamespace(init=lambda app:None)}):spec.loader.exec_module(self.bridge)
  self.modules=patch.dict(sys.modules,{'stock_bridge_test':self.bridge});self.modules.start();self.addCleanup(self.modules.stop)
  self.bridge.init(self.app);self.cfg=dict(enabled=True,generation='test',user_id=7,chat_id=7,bot_username='ownerbot',offset=0)
  self.bridge.store(self.app,self.cfg)
  self.local=patch.object(self.bridge,'local',return_value=view.render(state())).start();self.addCleanup(patch.stopall)
  self.request=patch.object(self.bridge,'request',return_value={}).start()
 def update(self,text='/stock',user=7,chat=7,kind='private',uid=1,callback=None):
  message={'message_id':10,'text':text,'from':{'id':user,'is_bot':False},'chat':{'id':chat,'type':kind}}
  if callback:return {'update_id':uid,'callback_query':{'id':'callback-1','data':callback,'from':message['from'],'message':message}}
  return {'update_id':uid,'message':message}
 def outbox(self):return self.app.rows('SELECT payload,state FROM telegram_outbox')
 def test_owner_command_queues_private_dashboard_once(self):
  update=self.update();self.bridge.receive(self.app,update);self.bridge.receive(self.app,update)
  self.local.assert_called_once_with(self.app,'stock101/crypto/telegram?mode=paper&view=status',timeout=12)
  rows=self.outbox();self.assertEqual(len(rows),1);payload=json.loads(rows[0]['payload']);self.assertEqual(payload['chat_id'],7);self.assertTrue(payload['protect_content'])
 def test_any_owner_message_containing_paper_word_gets_current_status(self):
  self.bridge.receive(self.app,self.update('지금 모의매매 어떻게 되고 있어?'))
  self.local.assert_called_once_with(self.app,'stock101/crypto/telegram?mode=paper&view=status',timeout=12)
  self.assertEqual(len(self.outbox()),1)
 def test_strangers_groups_and_wrong_owner_chat_cannot_inspect(self):
  for i,params in enumerate([dict(user=8),dict(chat=8),dict(kind='group'),dict(kind='supergroup')],1):self.bridge.receive(self.app,self.update(uid=i,**params))
  self.local.assert_not_called();self.assertEqual(self.outbox(),[])
 def test_owner_callback_gets_ack_and_only_a_read(self):
  self.bridge.receive(self.app,self.update(callback='st101:live:positions'))
  self.request.assert_called_once();self.assertEqual(self.request.call_args.args[1],'answerCallbackQuery')
  self.local.assert_called_once_with(self.app,'stock101/crypto/telegram?mode=live&view=positions',timeout=12)
  self.assertEqual(len(self.outbox()),1)
 def test_unauthorized_callback_cannot_read_or_send(self):
  self.bridge.receive(self.app,self.update(user=8,callback='st101:paper:status'))
  self.local.assert_not_called();self.request.assert_not_called();self.assertEqual(self.outbox(),[])
 def test_unknown_trade_command_and_malicious_callback_never_fall_through(self):
  self.bridge.receive(self.app,self.update('/stock live buy BTC',uid=1))
  self.bridge.receive(self.app,self.update(callback='st101:live:start',uid=2))
  self.local.assert_not_called();self.assertEqual(len(self.outbox()),2)
 def test_forwarded_command_is_not_executed(self):
  update=self.update();update['message']['forward_origin']={'type':'user'};self.bridge.receive(self.app,update);self.local.assert_not_called()
 def test_deep_link_and_bot_mention_route_to_dashboard(self):
  for i,text in enumerate(['/start stock101','/stock@ownerbot','/stock101 live strategies'],1):self.bridge.receive(self.app,self.update(text,uid=i))
  self.assertEqual(self.local.call_count,3);self.assertEqual(len(self.outbox()),3)
 def test_existing_approval_callback_keeps_original_behavior(self):
  self.local.return_value={'status':'done'};self.bridge.receive(self.app,self.update(callback='approve:'+'a'*32))
  self.local.assert_called_once_with(self.app,'decision',{'id':'a'*32,'approve':True})
 def test_connection_failure_has_safe_read_only_message(self):
  self.local.side_effect=TimeoutError('private secret');self.bridge.receive(self.app,self.update())
  text=json.loads(self.outbox()[0]['payload'])['text'];self.assertNotIn('private secret',text);self.assertIn('상태 조회',text)
 def test_delivery_keeps_privacy_flag_and_configured_chat(self):
  self.bridge.receive(self.app,self.update());self.bridge.deliver(self.app,self.cfg)
  self.assertEqual(self.request.call_args.args[1],'sendMessage');self.assertTrue(self.request.call_args.args[2]['protect_content']);self.assertEqual(self.request.call_args.args[2]['chat_id'],7)
  self.assertEqual(self.outbox()[0]['state'],'sent')

if __name__=='__main__':unittest.main()
