import sys

if 'pipeline' not in sys.path:
    sys.path.append('../../')

if 'FinRL_Library_master' not in sys.path:
    sys.path.append('../../FinRL_Library_master')

if 'ElegantRL_master' not in sys.path:
    sys.path.append('../../ElegantRL_master')

import shutil

from pipeline.utils.datetime import get_datetime_from_date_str, time_point, get_begin_vali_date_list

from pipeline.stock_data import StockData
from pipeline.elegant.env_predict import StockTradingEnvPredict

from pipeline.elegant.run import *
from elegantrl.agent import AgentPPO, AgentDDPG
from env_train import StockTradingEnv

if __name__ == '__main__':

    config.IF_SHOW_PREDICT_INFO = False

    # 4月16日向前，20,30,40,50,60,72,90周期
    # end_vali_date = get_datetime_from_date_str('2021-04-16')
    # 预测的截止日期
    end_vali_date = get_datetime_from_date_str(config.END_DATE)

    # 获取7个日期list
    list_begin_vali_date = get_begin_vali_date_list(end_vali_date)

    # ----
    # 从1万-2k万
    initial_capital = 40000000

    # 循环 vali_date_list 训练7次
    for begin_vali_item in list_begin_vali_date:
        # 从100到1k
        max_stock = 1000
        # max_stock = rd.randint(100, 300)
        # print('random max_stock', max_stock)

        torch.cuda.empty_cache()

        work_days, begin_date = begin_vali_item

        # 更新工作日标记，用于 run.py 加载训练过的 weights 文件
        config.WORK_DAY_FLAG = str(work_days)

        model_folder_path = f'./AgentPPO/hs300_{config.WORK_DAY_FLAG}'

        if not os.path.exists(model_folder_path):
            os.makedirs(model_folder_path)
            pass

        print('# work_days', work_days)
        print('# model_folder_path', model_folder_path)
        print('# initial_capital', initial_capital)
        print('# max_stock', max_stock)

        # 开始预测的日期
        config.START_EVAL_DATE = str(begin_date)

        # Agent
        args = Arguments(if_on_policy=True)
        args.agent = AgentPPO()  # AgentSAC(), AgentTD3(), AgentDDPG()
        args.agent.if_use_gae = True
        args.agent.lambda_entropy = 0.04

        # 沪深300
        # config.HS300_CODE_LIST = StockData.download_hs300_code_list()
        config.HS300_CODE_LIST = StockData.get_hs300_code_from_sqlite()

        tickers = config.HS300_CODE_LIST

        tech_indicator_list = [
            'macd', 'boll_ub', 'boll_lb', 'rsi_30', 'cci_30', 'dx_30',
            'close_30_sma', 'close_60_sma']  # finrl.config.TECHNICAL_INDICATORS_LIST

        gamma = 0.99
        # max_stock = 1e2
        # max_stock = 100
        # initial_capital = 100000
        initial_stocks = np.zeros(len(tickers), dtype=np.float32)
        buy_cost_pct = 0.0003
        sell_cost_pct = 0.0003
        start_date = config.START_DATE
        start_eval_date = config.START_EVAL_DATE
        end_eval_date = config.END_DATE

        args.env = StockTradingEnv(cwd='./datasets', gamma=gamma, max_stock=max_stock,
                                   initial_capital=initial_capital,
                                   buy_cost_pct=buy_cost_pct, sell_cost_pct=sell_cost_pct, start_date=start_date,
                                   end_date=start_eval_date, env_eval_date=end_eval_date, ticker_list=tickers,
                                   tech_indicator_list=tech_indicator_list, initial_stocks=initial_stocks,
                                   if_eval=False)

        # eval
        # max_stock = 100
        # initial_capital = 20000

        args.env_eval = StockTradingEnvPredict(cwd='./datasets', gamma=gamma, max_stock=max_stock,
                                               initial_capital=initial_capital,
                                               buy_cost_pct=buy_cost_pct, sell_cost_pct=sell_cost_pct,
                                               start_date=start_date,
                                               end_date=start_eval_date, env_eval_date=end_eval_date,
                                               ticker_list=tickers,
                                               tech_indicator_list=tech_indicator_list,
                                               initial_stocks=initial_stocks,
                                               if_eval=True)

        args.env.target_reward = 3
        args.env_eval.target_reward = 3

        # Hyperparameters
        args.gamma = gamma
        # ----
        # args.break_step = int(5e6)
        args.break_step = int(3e6)
        # ----

        args.net_dim = 2 ** 9
        args.max_step = args.env.max_step

        # ----
        # args.max_memo = args.max_step * 4
        args.max_memo = (args.max_step - 1) * 8
        # ----

        # ----
        # args.batch_size = 2 ** 10
        args.batch_size = 2 ** 11
        # ----

        # ----
        # args.repeat_times = 2 ** 3
        args.repeat_times = 2 ** 4
        # ----

        args.eval_gap = 2 ** 4
        args.eval_times1 = 2 ** 3
        args.eval_times2 = 2 ** 5

        # ----
        # args.if_allow_break = False
        args.if_allow_break = True
        # ----

        args.rollout_num = 4  # the number of rollout workers (larger is not always faster)

        # train_and_evaluate(args)
        train_and_evaluate_mp(args)  # the training process will terminate once it reaches the target reward.

        # 保存训练后的模型
        model_file_path = f'./AgentPPO/hs300_{config.WORK_DAY_FLAG}/actor.pth'
        shutil.copyfile('./AgentPPO/StockTradingEnv-v1_0/actor.pth', model_file_path)

        # 保存训练曲线图
        # plot_learning_curve.jpg
        timepoint_temp = time_point()
        plot_learning_curve_file_path = f'./AgentPPO/hs300_{config.WORK_DAY_FLAG}/plot_{timepoint_temp}.jpg'
        shutil.copyfile('./AgentPPO/StockTradingEnv-v1_0/plot_learning_curve.jpg', plot_learning_curve_file_path)

        # recorder.npy
        pass
    pass