import tiktoken

def get_tokenizer(model:str):
    try:
        encoding = tiktoken.encoding_for_model(model)
        return encoding.encode
    except:
        encoding = tiktoken.get_encoding("cl100k_base")
        return encoding.encode
def calculate_token(text:str,model:str)->int:
    tokenizer = get_tokenizer(model)
    if tokenizer:
        return len(tokenizer(text))
    return est_token(text)
def est_token(text:str)->int:
    return max(1,len(text)//4)