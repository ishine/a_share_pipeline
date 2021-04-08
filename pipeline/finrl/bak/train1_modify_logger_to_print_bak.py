import logging
import os
import random
import time

import pandas as pd
import numpy as np

import argparse

import sys

import torch

if 'pipeline' not in sys.path:
    sys.path.append('../../')

if 'Informer2020_main' not in sys.path:
    sys.path.append('../../Informer2020_main')

if 'FinRL_Library_master' not in sys.path:
    sys.path.append('../../FinRL_Library_master')

from pipeline.finrl import config
from pipeline.stock_data import StockData
from pipeline.utils.log import get_logger

from pipeline.finrl.models import DRLAgent
from FinRL_Library_master.finrl.preprocessing.preprocessors import FeatureEngineer

from pipeline.finrl.env_stocktrading import StockTradingEnv
from pipeline.utils import datetime

if __name__ == "__main__":

    torch.cuda.empty_cache()

    # 多进程id标识
    # multiprocess_id = datetime.time_point().replace('_', '')
    multiprocess_id = '1'

    parser = argparse.ArgumentParser(description='finrl')
    parser.add_argument('--multiprocess_id', type=str, default=multiprocess_id, help='multiprocess id')
    parser.add_argument('--download_data', type=bool, default=False, help='download data')

    args = parser.parse_args()

    print(args)

    # 创建目录
    if not os.path.exists("./" + config.DATA_SAVE_DIR):
        os.makedirs("./" + config.DATA_SAVE_DIR)
    if not os.path.exists("./" + config.TRAINED_MODEL_DIR):
        os.makedirs("./" + config.TRAINED_MODEL_DIR)
    if not os.path.exists("./" + config.TENSORBOARD_LOG_DIR):
        os.makedirs("./" + config.TENSORBOARD_LOG_DIR)
    if not os.path.exists("./" + config.RESULTS_DIR):
        os.makedirs("./" + config.RESULTS_DIR)
    if not os.path.exists("./" + config.LOGGER_DIR):
        os.makedirs("./" + config.LOGGER_DIR)

    # 日志
    logger = get_logger(log_file_path=f'./{config.LOGGER_DIR}/{args.multiprocess_id}_TRAIN_SAC.log', log_level=logging.INFO)

    # 股票代码
    stock_code = 'sh.600036'

    # 训练开始日期
    start_date = "2002-05-01"
    # 停止训练日期 / 开始预测日期
    start_trade_date = "2021-03-08"
    # 停止预测日期
    end_date = '2021-04-07'

    # 今天日期，交易日
    # today_date = '2021-03-09'

    # 今日开盘价
    # today_open_price = 50.02

    # 现金金额
    initial_amount = 100000

    # 训练次数
    total_timesteps = int(1e5)

    print("==============下载A股数据==============")
    if args.download_data:
        # 下载A股的日K线数据
        stock_data = StockData(output_dir="./" + config.DATA_SAVE_DIR, date_start=start_date, date_end=end_date)
        # 获得数据文件路径
        csv_file_path = stock_data.download(stock_code, fields=stock_data.fields_day)
    else:
        csv_file_path = f"./{config.DATA_SAVE_DIR}/{stock_code}.csv"
    pass

    # csv_file_path = './datasets_temp/sh.600036.csv'
    print("==============处理未来数据==============")

    # open今日开盘价为T日数据，其余皆为T-1日数据，避免引入未来数据
    df = pd.read_csv(csv_file_path)

    # 删除未来数据，把df分为2个表，日期date+开盘open是A表，其余的是B表
    df_left = df.drop(df.columns[2:], axis=1)

    df_right = df.drop(['date', 'open'], axis=1)

    # 删除A表第一行
    df_left.drop(df_left.index[0], inplace=True)
    df_left.reset_index(drop=True, inplace=True)

    # 删除B表最后一行
    df_right.drop(df_right.index[-1:], inplace=True)
    df_right.reset_index(drop=True, inplace=True)

    # 将A表和B表重新拼接，剔除了未来数据
    df = pd.concat([df_left, df_right], axis=1)

    # # 今天的数据，date、open为空，重新赋值
    # df.loc[df.index[-1:], 'date'] = today_date
    # df.loc[df.index[-1:], 'open'] = today_open_price

    # 缓存文件，debug用
    # df.to_csv(f'{config.DATA_SAVE_DIR}/{stock_code}_concat_df.csv', index=False)

    print("==============加入技术指标==============")
    fe = FeatureEngineer(
        use_technical_indicator=True,
        tech_indicator_list=config.TECHNICAL_INDICATORS_LIST,
        use_turbulence=False,
        user_defined_feature=False,
    )

    df_fe = fe.preprocess_data(df)
    df_fe['log_volume'] = np.log(df_fe.volume * df_fe.close)
    df_fe['change'] = (df_fe.close - df_fe.open) / df_fe.close
    df_fe['daily_variance'] = (df_fe.high - df_fe.low) / df_fe.close

    # df_fe.to_csv(f'{config.DATA_SAVE_DIR}/{stock_code}_processed_df.csv', index=False)

    print("==============拆分 训练/预测 数据集==============")
    # Training & Trading data split
    df_train = df_fe[(df_fe.date >= start_date) & (df_fe.date < start_trade_date)]
    df_train = df_train.sort_values(["date", "tic"], ignore_index=True)
    df_train.index = df_train.date.factorize()[0]

    df_predict = df_fe[(df_fe.date >= start_trade_date) & (df_fe.date <= end_date)]
    df_predict = df_predict.sort_values(["date", "tic"], ignore_index=True)
    df_predict.index = df_predict.date.factorize()[0]

    print("==============数据准备完成==============")
    print("==============开始循环==============")

    # 训练/预测 时间点
    # time_point = time.strftime("%Y%m%d_%H%M%S", time.localtime())
    # time_point = datetime.time_point()
    time_point = '1'

    for j in range(10):

        for i in range(6):

            logger.info('*' * 20 + ' [ ' + str(j) + '-' + str(i) + ' ] ' + '*' * 20)

            logger.info(time_point)

            # 最后资产
            last_account_value = 0

            print("==============修改 SAC_PARAMS 参数==============")

            # 每次梯度更新的最小批量
            # :param batch_size: Minibatch size for each gradient update
            # int = 256
            # 随机选择 64, 128, 256
            sac_batch_size = 64
            # sac_batch_size = random.choice([64, 128])

            #     :param learning_rate: learning rate for adam optimizer,
            #         the same learning rate will be used for all networks (Q-Values, Actor and Value function)
            #         it can be a function of the current progress remaining (from 1 to 0)
            # 3e-4
            # 随机数 0.0001 - 0.0003
            # sac_learning_rate = random.uniform(0.0003, 0.001)
            sac_learning_rate_scale = 0.0001 * i
            sac_learning_rate = 0.0006 - sac_learning_rate_scale

            # 在学习开始之前，模型收集过渡需要多少步骤
            # :param learning_starts: how many steps of the model to collect transitions for before learning starts
            # int = 100
            # sac_learning_starts = random.randint(200, 1000)
            sac_learning_starts = 200

            # 熵的正则化系数。（相当于原始SAC论文中的奖励比例的逆量。）控制勘探权衡。将其设置为“自动”以自动学习（以及“auto_0.1”以使用0.1作为初始值）
            # 熵正则化系数。（相当于原始SAC论文中奖励规模的倒数。）控制勘探/开发权衡。将其设置为“auto”以自动学习（使用0.1作为初始值时设置为“auto\u 0.1”）
            #     :param ent_coef: Entropy regularization coefficient. (Equivalent to
            #         inverse of reward scale in the original SAC paper.)  Controlling exploration/exploitation trade-off.
            #         Set it to 'auto' to learn it automatically (and 'auto_0.1' for using 0.1 as initial value)
            # sac_ent_coef = random.choice(["auto_0.1", "auto"])
            sac_ent_coef = "auto_0.1"

            # :param buffer_size: size of the replay buffer
            # int(1e6)
            # sac_buffer_size = random.randint(int(1e6), int(1e8))
            sac_buffer_size = 100000

            config.SAC_PARAMS = {
                "batch_size": sac_batch_size,
                "buffer_size": sac_buffer_size,
                "learning_rate": sac_learning_rate,
                "learning_starts": sac_learning_starts,
                "ent_coef": sac_ent_coef,
            }

            logger.info('SAC_PARAMS:' + str(config.SAC_PARAMS))

            # print("==============修改 hmax 单支股票最大股数==============")
            # 单次、单支、允许购买的最大股数，非金额
            # 例如单次购买1000股。1000×50元=5万元
            # hmax = random.randint(1500, 10000)
            hmax = 10000

            print("==============修改 reward_scaling 奖励系数==============")

            # 奖励系数，从 1e-4 到 1.0
            # reward_scaling = random.uniform(0.3, 2.0)
            reward_scaling = 1.0

            # 选择模型

            # -----------------sac-----------------
            model_name = "sac"
            model_kwargs = config.SAC_PARAMS
            # -------------------------------------

            # 统一的文件名
            uniform_file_name = f"mpid_{args.multiprocess_id}_tp_{time_point}_{model_name}_{str(total_timesteps // 1000) + 'k'}"

            print("==============修改 env_kwargs 参数==============")

            # calculate state action space
            stock_dimension = len(df_train.tic.unique())
            state_space = (1 + 2 * stock_dimension + len(config.TECHNICAL_INDICATORS_LIST) * stock_dimension)

            env_kwargs = {
                "hmax": hmax,
                "initial_amount": initial_amount,
                "buy_cost_pct": 0.0,
                "sell_cost_pct": 0.003,
                "state_space": state_space,
                "stock_dim": stock_dimension,
                "tech_indicator_list": config.TECHNICAL_INDICATORS_LIST,
                "action_space": stock_dimension,
                "reward_scaling": reward_scaling,
                "model_name": model_name,
                "mode": 'normal_env',
                "iteration": str(total_timesteps // 1000) + 'k',
                'uniform_file_name': uniform_file_name
            }

            logger.info('env_kwargs:' + str(env_kwargs))

            e_train_gym = StockTradingEnv(df=df_train, random_start=True, **env_kwargs)
            env_train, _ = e_train_gym.get_sb_env()
            agent_train = DRLAgent(env=env_train)

            model_object = agent_train.get_model(model_name=model_name, model_kwargs=model_kwargs)

            # weights文件名
            weights_file_path = f"{config.TRAINED_MODEL_DIR}/{uniform_file_name}"
            # weights_file_path = f"{config.TRAINED_MODEL_DIR}/mpid_2_tp_20210404_171734_sac_100k.zip"

            # 加载训练好的weights文件，可接续上次的结果继续训练。
            zip_file_path = weights_file_path + '.zip'
            if os.path.exists(zip_file_path):
                model_object.load(weights_file_path)
                print('> 找到 weights 文件:', zip_file_path)
            else:
                print('> 未找到 weights 文件:', zip_file_path)
            pass

            print("==============开始训练模型==============")

            try:
                # 训练模型
                model_object = agent_train.train_model(model=model_object, tb_log_name=model_name,
                                                       total_timesteps=total_timesteps)

                # 保存训练好的weights文件
                model_object.save(weights_file_path)
                print('weights文件保存在:', weights_file_path)

                print("==============模型训练完成==============")

                # 预测
                print("==============开始预测==============")

                # debug
                # df_predict.to_csv(f'{config.DATA_SAVE_DIR}/{stock_code}_trade_df.csv', index=False)

                # 开启 湍流阈值
                # e_trade_gym = StockTradingEnv(df=df_trade, turbulence_threshold=250, **env_kwargs)

                # 不使用 湍流阈值
                e_trade_gym = StockTradingEnv(df=df_predict, random_start=False, **env_kwargs)
                env_trade, obs_trade = e_trade_gym.get_sb_env()
                agent_predict = DRLAgent(env=env_trade)

                model_predict = agent_predict.get_model(model_name, model_kwargs=model_kwargs)

                # 加载训练好的weights文件
                model_predict.load(weights_file_path)

                df_account_value, df_actions = DRLAgent.DRL_prediction(model=model_predict, environment=e_trade_gym)

                # 获取最后的资产总数，记录下来
                last_row = df_account_value.loc[df_account_value.index[-1:], 'account_value']
                last_account_value = list(last_row)[0]

                # 记录最后资产数和参数
                logger.info('>' * 10 + ' last_account_value:' + str(last_account_value) + '\n')

                # 如果最后资产大于初始资金
                if last_account_value > initial_amount:
                    # 使用不同时间点，保存所有的文件
                    time_point2 = datetime.time_point().replace('_', '')

                    account_csv_file_path = f"{config.RESULTS_DIR}/{uniform_file_name}_final_df_account_value_{time_point2}.csv"
                    df_account_value.to_csv(account_csv_file_path)

                    actions_csv_file_path = f"{config.RESULTS_DIR}/{uniform_file_name}_final_df_actions_{time_point2}.csv"
                    df_actions.to_csv(actions_csv_file_path)

                    print("account 结果保存在:", account_csv_file_path)
                    print("actions 结果保存在:", actions_csv_file_path)
                    pass
                else:
                    print('最后资产小于初始资金，不保存结果：', last_account_value)
                    pass
                pass

                print("==============预测完成==============")

                # # 如果最后的资金大于2倍初始资金，则结束循环
                # if last_account_value >= 2 * initial_amount:
                #     break
                # else:
                #     pass
                # pass
            except Exception as ex:
                logger.error(str(ex))
                pass
            finally:
                torch.cuda.empty_cache()
                pass
            pass
        pass

    pass
