import chromadb

client = chromadb.PersistentClient(path="chroma_db")
collection = client.get_collection(name="philosophy")

query = "Tomorrow we’re throwing a party for someone who has always been there for me, and I’m so thankful for her"
results = collection.query(query_texts=[query], n_results=3, 
    where={"author": "Marcus Aurelius"},)
print(results)