import typer

app = typer.Typer()

@app.command()
def chat():
    print("Tiaga CLI working")

if __name__ == "__main__":
    app()