from models.emulator import Emulator, get_target_path
from experiments.hydrology.experiment_config import get_config
import argparse
import os
import ray
import pickle
import shutil
import logging

os.environ["CUDA_VISIBLE_DEVICES"] = "7"


def parse_args():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        '--config_name',
        '-c',
        type=str,
        help='Configuration name.',
        default='default'
    )

    parser.add_argument(
        '--overwrite',
        '-O',
        help='Flag to overwrite existing runs (all existing runs will be lost!).',
        action='store_true'
    )

    parser.add_argument(
        '--small_aoi',
        '-T',
        help='Flag to perform a test run; only a fraction of the data is evaluated in each epoch.',
        action='store_true'
    )

    parser.add_argument(
        '--permute',
        help='Whether to permute the sequence of input of output data during training.',
        action='store_true'
    )

    args = parser.parse_args()

    if args.small_aoi:
        logging.warning(
            'Running experiment in test mode; Not all data is used for training!')

    return args


def load_best_config(store):
    best_config = os.path.join(store, 'summary/best_params.pkl')
    if not os.path.isfile(best_config):
        raise ValueError(
            'Tried to load best model config, file does not exist:\n'
            f'{best_config}\nRun `summarize_results.py` to create '
            'such a file.'
        )
    with open(best_config, 'rb') as f:
        config = pickle.load(f)

    return config


def tune(args):

    config = get_config(args.config_name)
    config.update({'is_tune': False})

    model_tune_store = get_target_path(config, args, mode='modeltune')
    model_restore_path = os.path.join(
        model_tune_store,
        'model.pth'
    )
    store = get_target_path(config, args, mode='inference')
    prediction_file = f'{store}predictions.zarr'

    if args.overwrite:
        if os.path.isdir(store):
            shutil.rmtree(store)
    else:
        if os.path.isdir(store):
            raise ValueError(
                f'The directory {store} exists. Set flag "--overwrite" '
                'if you want to overwrite runs - all existing runs will be lost!')
    os.makedirs(store)

    if os.path.isdir(prediction_file):
        shutil.rmtree(prediction_file)

    best_config = load_best_config(model_tune_store)
    best_config.update({
        'fold': -1,
        'hc_config': config
    })

    config.update({
        'store': store,
        'small_aoi': args.small_aoi,
        'permute': args.permute
    })

    # Inference is a single run, we can use more resources.
    best_config['hc_config']['ncpu_per_run'] = 60
    best_config['hc_config']['ngpu_per_run'] = 1
    best_config['hc_config']['num_workers'] = 20
    best_config['hc_config']['batch_size'] = 200

    print('Restoring model from: ', model_restore_path)
    e = Emulator(best_config)
    e._restore(model_restore_path)
    e._predict(prediction_file)
    #predictions.to_netcdf(os.path.join(store, 'predictions.nc'))

    # summarize_run(store)


if __name__ == '__main__':
    args = parse_args()

    ray.init(include_webui=False, object_store_memory=int(5e9))

    tune(args)

    ray.shutdown()
