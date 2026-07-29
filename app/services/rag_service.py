from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.config import Settings
from app.models.schemas import ChatResponse, Source

if TYPE_CHECKING:
    from langchain_chroma import Chroma
    from langchain_community.embeddings import HuggingFaceEmbeddings
    from langchain_core.documents import Document


class RAGService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._embeddings: HuggingFaceEmbeddings | None = None

    @property
    def embeddings(self) -> HuggingFaceEmbeddings:
        from langchain_community.embeddings import HuggingFaceEmbeddings

        if self._embeddings is None:
            self._embeddings = HuggingFaceEmbeddings(
                model_name="sentence-transformers/all-MiniLM-L6-v2",
                model_kwargs={"device": "cpu"},
                encode_kwargs={"normalize_embeddings": True},
            )
        return self._embeddings

    def _vector_store(self) -> Chroma:
        from langchain_chroma import Chroma

        return Chroma(
            collection_name=self.settings.chroma_collection,
            persist_directory=str(self.settings.chroma_path),
            embedding_function=self.embeddings,
        )

    def answer(self, question: str) -> ChatResponse:
        if not self.settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured. Add it to your .env file.")

        documents = self._vector_store().similarity_search(question, k=self.settings.top_k)
        if not documents:
            return ChatResponse(
                answer="I could not find relevant information in the uploaded documents.",
                sources=[],
            )

        from langchain_core.messages import HumanMessage, SystemMessage
        from langchain_openai import ChatOpenAI

        context = self._format_context(documents)
        llm = ChatOpenAI(
            model=self.settings.openai_model,
            api_key=self.settings.openai_api_key,
            temperature=0,
        )
        response = llm.invoke(
            [
                SystemMessage(
                    content=(
                        "You answer questions using only the supplied document context. "
                        "If the context does not answer the question, say that clearly. "
                        "Do not invent facts or citations. Keep the answer concise."
                    )
                ),
                HumanMessage(content=f"Question: {question}\n\nDocument context:\n{context}"),
            ]
        )
        answer = response.content if isinstance(response.content, str) else str(response.content)
        return ChatResponse(answer=answer, sources=self._sources(documents))

    @staticmethod
    def _format_context(documents: list[Document]) -> str:
        entries: list[str] = []
        for document in documents:
            filename = document.metadata.get("filename", "Unknown")
            page = document.metadata.get("page")
            page_label = f", page {page}" if page else ""
            entries.append(f"[Source: {filename}{page_label}]\n{document.page_content}")
        return "\n\n".join(entries)

    @staticmethod
    def _sources(documents: list[Document]) -> list[Source]:
        seen: set[tuple[str, int | None, str]] = set()
        sources: list[Source] = []
        for document in documents:
            filename = str(document.metadata.get("filename", "Unknown"))
            page = document.metadata.get("page")
            excerpt = " ".join(document.page_content.split())[:300]
            key = (filename, page, excerpt)
            if key not in seen:
                seen.add(key)
                sources.append(Source(filename=filename, excerpt=excerpt, page=page))
        return sources
