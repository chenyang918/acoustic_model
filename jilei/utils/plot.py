from pathlib import Path
import numpy as np
import torch
from torch.autograd import Variable
from visdom import Visdom

from .logger import logger

viz = Visdom()
viz_wins = dict()
result_dir = Path.cwd()


def visualize_setup(image_dir):
    assert viz.check_connection(), "visdom server is not working!"
    try:
        global result_dir
        Path.mkdir(Path(image_dir), parents=True, exist_ok=True)
        result_dir = image_dir
    except:
        raise()


def viz_plot(win, func, *args, **kwargs):
    try:
        func(*args, win=viz_wins[win], **kwargs)
    except:
        viz_wins[win] = func(*args, **kwargs)


def plot_samples(ssvae):
    """
    This is a method to do conditional sampling in visdom
    """
    ys = {}
    for i in range(10):
        ys[i] = Variable(torch.zeros(1, 10))
        ys[i][0, i] = 1

    for i in range(10):
        images = []
        for rr in range(100):
            _, sample_mu_i = ssvae.model_sample(ys[i])
            img = sample_mu_i[0].view(1, 28, 28).cpu().data.numpy()
            images.append(img)
        viz_plot(f"sample{i}", viz.images, images, 10, 2)


def plot_llk(train_elbo, test_elbo):
    import matplotlib.pyplot as plt
    import scipy as sp
    import seaborn as sns
    import pandas as pd
    plt.figure(figsize=(30, 10))
    sns.set_style("whitegrid")
    data = np.concatenate([np.arange(len(test_elbo))[:, sp.newaxis], -test_elbo[:, sp.newaxis]], axis=1)
    df = pd.DataFrame(data=data, columns=['Training Epoch', 'Test ELBO'])
    g = sns.FacetGrid(df, size=10, aspect=1.5)
    g.map(plt.scatter, "Training Epoch", "Test ELBO")
    g.map(plt.plot, "Training Epoch", "Test ELBO")
    plt.savefig(str(Path(result_dir, 'test_elbo_vae.png')))
    plt.close('all')


def plot_tsne(ssvae, test_loader, use_cuda=False):
    xs = test_loader.dataset.test_data.float()
    ys = test_loader.dataset.test_labels
    z_mu, z_sigma = ssvae.guide_sample(xs, ys, len(test_loader))

    z_states = z_mu.data.cpu().numpy()
    classes = ys.cpu().numpy()

    logger.info("calculating T-SNE of z embedding..")
    if use_cuda:
        import t_sne_bhcuda.bhtsne_cuda as tsne_bhcuda
        files_dir = Path.cwd() / "tsne"
        Path.mkdir(files_dir, parents=True, exist_ok=True)
        z_embed = tsne_bhcuda.t_sne(z_states, no_dims=2, files_dir=files_dir, gpu_mem=0.9)
        z_embed = np.array([list(x) for x in z_embed])
    else:
        from sklearn.manifold import TSNE
        model_tsne = TSNE(n_components=2, random_state=0)
        z_embed = model_tsne.fit_transform(z_states)

    __plot_tsne_to_visdom(z_embed, classes)
    #__plot_tsne_to_matplotlib(z_embed, classes)


def __plot_tsne_to_visdom(z_embed, classes):
    import colorlover as cl

    C = np.array([list(x) for x in cl.to_numeric(cl.scales['10']['qual']['Paired'])]).astype(int)

    for ic in range(10):
        idx = classes[:, ic] == 1
        X = z_embed[idx, :]
        Y = np.ones_like(X[:, 0]).astype(int)   # treat as a single class
        Ci = np.expand_dims(C[ic], axis=0)      # pickup a corresponding color
        viz_plot(f"z_tsne_for_{ic}", viz.scatter, X, Y,
                 opts=dict(markercolor=Ci, markersize=4, legend=[str(ic)]))

    X = z_embed
    Y = np.argmax(classes, axis=1) + 1
    viz_plot("z_tsne", viz.scatter, X, Y,
             opts=dict(width=800, height=800, markercolor=C, markersize=4,
                       legend=[str(x) for x in range(10)]))


def __plot_tsne_to_matplotlib(z_embed, classes):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    figs = plt.figure(0)
    plt.clf()

    for ic in range(10):
        ind_class = classes[:, ic] == 1
        color = plt.cm.Set1(ic)

        fig = plt.figure(ic + 1)
        plt.clf()
        plt.scatter(z_embed[ind_class, 0], z_embed[ind_class, 1], s=10, color=color)
        plt.title(f"Latent Variable T-SNE per Class: {ic}")
        fig.savefig(str(Path(result_dir, f"z_embedding_{ic}.png")))

        figs = plt.figure(0)
        plt.scatter(z_embed[ind_class, 0], z_embed[ind_class, 1], s=10, color=color)

    figs = plt.figure(0)
    plt.title(f"Latent Variable T-SNE for All Classes")
    figs.savefig(str(Path(result_dir, f"z_embedding_all.png")))


if __name__ == "__main__":
    import argparse
    from ssvae import SsVae
    from mnist_cached import MNISTCached, setup_data_loaders

    parser = argparse.ArgumentParser(description="SS-VAE plot")
    parser.add_argument('--sup-num', default=3000, type=float, help="supervised amount of the data i.e. how many of the images have supervised labels")
    parser.add_argument('--batch-size', default=100, type=int, help="number of images (and labels) to be considered in a batch")
    parser.add_argument('--use-cuda', default=False, action='store_true', help="use cuda")
    parser.add_argument('--continue-from', default=None, type=str, help="model file path to make continued from")

    args = parser.parse_args()

    ss_vae = SsVae(**vars(args))

    if args.use_cuda:
        torch.set_default_tensor_type("torch.cuda.FloatTensor")

    data_loaders = setup_data_loaders(MNISTCached, args.use_cuda, args.batch_size,
                                      sup_num=args.sup_num, drop_last=True)

    plot_tsne(ss_vae, data_loaders["test"], use_cuda=args.use_cuda)

