from dataclasses import dataclass, field
from typing import List, Tuple, Dict

import polars as pl

import torch

from torch.utils.data import Dataset

import numpy as np

import pickle

from mlproject.data_processing import RawHumanChatBotData
from mlproject.embeddings import ArticleEmbedder


@dataclass
class HumanChatBotDataset(Dataset):
    """
    A PyTorch Dataset class for the Human Chat Bot dataset.
    Use this class when you want to load all the data and embeddings
    at once.
    """
    embeddings: List[torch.Tensor] = field(repr=False)
    labels: List[int] = field(repr=False)

    @staticmethod
    def find_classnum_mapping(data: pl.DataFrame) -> Dict[str, int]:
        """
        Find the mapping of article types to class numbers.
        """
        article_types = data["type"].unique().to_list()
        # sort them, so we always guarantee the same mapping
        article_types.sort()
        return {article_type: i for i, article_type in enumerate(article_types)}

    @classmethod
    def from_raw_data(
        cls,
        raw_data: RawHumanChatBotData,
        embedder: ArticleEmbedder
    ) -> "HumanChatBotDataset":
        print(
            f"Generating embeddings for the dataset {raw_data} using embedder {embedder.__class__.__name__}")
        embeddings = []
        labels = []
        article_type_to_classnum = cls.find_classnum_mapping(raw_data.data)
        for row in raw_data.data.iter_rows(named=True):
            text = row["text"]
            article_type = row["type"]
            label = article_type_to_classnum[article_type]
            embeddings.append(embedder.embed(text))
            labels.append(label)
        return cls(embeddings, labels)

    @classmethod
    def from_train_test_raw_data(
        cls,
        train_data: RawHumanChatBotData,
        test_data: RawHumanChatBotData,
        embedder: ArticleEmbedder
    ) -> Tuple["HumanChatBotDataset", "HumanChatBotDataset"]:
        train = cls.from_raw_data(
            train_data,
            embedder
        )
        test = cls.from_raw_data(
            test_data,
            embedder
        )
        return train, test

    @classmethod
    def load(cls, load_path: str) -> "HumanChatBotDataset":
        with open(load_path, "rb") as f:
            return pickle.load(f)

    def save(self, save_path: str):
        with open(save_path, "wb") as f:
            pickle.dump(self, f)

    @property
    def embedding_size(self) -> int:
        return len(self.embeddings[0])

    @property
    def number_of_classes(self) -> int:
        return len(set(self.labels))

    def __len__(self) -> int:
        return len(self.embeddings)

    def __getitem__(self, idx: int) -> Tuple[torch.Tensor, int]:
        return self.embeddings[idx], self.labels[idx]


@dataclass
class TwoDImagesDataset(Dataset):
    """Simple Dataset Wrapper that resizes
    the embedded vectors into a square image
    shape

    TODO: Consider experimenting with making
    images out of the embedding vectors.
    """

    dataset: HumanChatBotDataset

    def __len__(self):
        return len(self.dataset)

    def __getitem__(self, idx: int) -> Tuple[torch.Tensor, int]:
        embedding, label = self.dataset.__getitem__(idx)
        v_size = len(embedding)
        n = int(v_size**0.5)
        return embedding.reshape((1, n, n)), label


@dataclass
class LazyHumanChatBotDataset(Dataset):
    """
    A PyTorch Dataset class for the Human Chat Bot dataset.
    Use this class when you want to lazily embed
    data on the fly.

    Useful when there's a lot of data and creating all the 
    embeddings at once would be too memory intensive.
    """
    data: pl.DataFrame
    embedder: ArticleEmbedder = field(repr=False)
    article_type_to_classnum: Dict[str, int]

    def __post_init__(self):
        # assert that all types in the dataset
        # have a corresponding article type mapping
        types_in_dataset = self.data["type"].unique().to_list()
        missing_types = set(types_in_dataset) - \
            set(self.article_type_to_classnum.keys())
        if missing_types:
            raise ValueError(
                f"Missing classnumber for types: {missing_types}")

    def get_class_num(self, article_type: str) -> int:
        """
        Get the class number for the given article type.
        """
        return self.article_type_to_classnum[article_type]

    @classmethod
    def from_raw_data(
        cls,
        raw_data: RawHumanChatBotData,
        embedder: ArticleEmbedder,
        article_type_to_classnum: Dict[str, int]
    ) -> "LazyHumanChatBotDataset":
        return cls(
            raw_data.data,
            embedder,
            article_type_to_classnum
        )

    def __len__(self) -> int:
        return len(self.data)

    def __getitem__(self, idx: int) -> Tuple[np.ndarray, int]:
        row = self.data[idx]
        text = row["text"].item()
        article_type = row["type"].item()
        label = self.get_class_num(article_type)
        return self.embedder.embed(text), label
