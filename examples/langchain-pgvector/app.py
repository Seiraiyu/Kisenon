"""LangChain + langchain-postgres PGVectorStore on Kisenon.

usage:
  uv run python app.py ingest corpus/    chunk, embed locally (fastembed), store in Postgres
  uv run python app.py ask "question"    retrieve top 4; answer with Claude if ANTHROPIC_API_KEY
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from fastembed import TextEmbedding
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_postgres import PGEngine, PGVectorStore
from langchain_text_splitters import RecursiveCharacterTextSplitter

SCHEMA, TABLE, DIM = "langchain_pgvector", "docs", 384
MODEL = "claude-sonnet-5"


class LocalEmbeddings(Embeddings):
    """fastembed (BAAI/bge-small-en-v1.5, 384-d, CPU, no key) as a LangChain Embeddings."""

    def __init__(self) -> None:
        self._model = TextEmbedding("BAAI/bge-small-en-v1.5")

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [v.tolist() for v in self._model.embed(texts)]

    def embed_query(self, text: str) -> list[float]:
        return next(iter(self._model.query_embed(text))).tolist()


def load_docs(folder: Path) -> list[Document]:
    splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=100)
    docs = [
        Document(page_content=p.read_text(), metadata={"source": p.name})
        for p in sorted(folder.glob("*.md"))
    ]
    return splitter.split_documents(docs)


def format_docs(docs: list[Document]) -> str:
    return "\n\n".join(f"[{d.metadata['source']}]\n{d.page_content}" for d in docs)


def main(argv: list[str]) -> int:
    load_dotenv()
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL is not set (see README 'Setup').", file=sys.stderr)
        return 2
    if len(argv) != 2 or argv[0] not in ("ingest", "ask"):
        print(__doc__, file=sys.stderr)
        return 2
    command, arg = argv
    engine = PGEngine.from_connection_string(
        url=url.replace("postgresql://", "postgresql+psycopg://", 1)
    )
    embeddings = LocalEmbeddings()

    if command == "ingest":
        docs = load_docs(Path(arg))
        with psycopg.connect(url, autocommit=True) as conn:
            conn.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
        engine.init_vectorstore_table(TABLE, DIM, schema_name=SCHEMA, overwrite_existing=True)
        store = PGVectorStore.create_sync(
            engine=engine, embedding_service=embeddings, table_name=TABLE, schema_name=SCHEMA
        )
        store.add_documents(docs)
        print(f"Ingested {len(docs)} chunks into {SCHEMA}.{TABLE}")
        print(json.dumps({"chunks": len(docs), "table": f"{SCHEMA}.{TABLE}"}))
        return 0

    store = PGVectorStore.create_sync(
        engine=engine, embedding_service=embeddings, table_name=TABLE, schema_name=SCHEMA
    )
    docs = store.as_retriever(search_kwargs={"k": 4}).invoke(arg)
    answer = None
    if os.environ.get("ANTHROPIC_API_KEY"):
        from langchain_anthropic import ChatAnthropic

        prompt = ChatPromptTemplate.from_messages([
            ("system", "Answer only from this context and cite sources as [file].\n\n{context}"),
            ("human", "{question}"),
        ])
        chain = prompt | ChatAnthropic(model=MODEL) | StrOutputParser()
        answer = chain.invoke({"context": format_docs(docs), "question": arg})
        print(answer)
    else:
        print("[no ANTHROPIC_API_KEY: printing retrieved chunks]", file=sys.stderr)
        print(format_docs(docs))
    print(json.dumps({"question": arg, "answer": answer,
                      "sources": [d.metadata["source"] for d in docs]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
