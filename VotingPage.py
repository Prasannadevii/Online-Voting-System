import tkinter as tk
from tkinter import *
from PIL import ImageTk, Image

def voteCast(root, frame1, vote, client_socket):
    for widget in frame1.winfo_children():
        widget.destroy()

    client_socket.send(vote.encode())  # send vote
    message = client_socket.recv(1024).decode()  # receive success/fail message
    print(message)

    if message == "Successful":
        Label(frame1, text="Vote Casted Successfully", font=('Helvetica', 18, 'bold')).grid(row=1, column=1)
    else:
        Label(frame1, text="Vote Cast Failed... \nTry again", font=('Helvetica', 18, 'bold')).grid(row=1, column=1)

    client_socket.close()


def votingPg(root, frame1, client_socket):
    root.title("Cast Vote")

    for widget in frame1.winfo_children():
        widget.destroy()

    Label(frame1, text="Cast Vote", font=('Helvetica', 18, 'bold')).grid(row=0, column=1, pady=10)

    # Define parties: text, value, image file
    parties = [
        ("TVK\nVijay", "tvk", "img/tvk.jpg"),
        ("DMK\nM K Stalin", "dmk", "img/dmk.jpg"),
        ("AIADMK\nEdappadi K Palanisamy", "aiadmk", "img/aiadmk.jpg"),
        ("BJP\nNarendra Modi", "bjp", "img/bjp.png"),
        ("Congress\nRahul Gandhi", "cong", "img/cong.jpg"),
        # Add more parties here if needed
        # ("Aam Aadmi Party\nArvind Kejriwal", "aap", "img/aap.png"),
        # ("Shiv Sena\nUdhav Thakrey", "ss", "img/ss.png"),
        # ("NOTA", "nota", "img/nota.jpg")
    ]

    vote = StringVar(frame1, "-1")

    # Dynamically create buttons and images
    for idx, (name, value, img_path) in enumerate(parties):
        row = idx + 1  # start from row 1
        # Create button
        btn = Radiobutton(frame1, text=name, variable=vote, value=value,
                          indicator=0, height=4, width=20,
                          command=lambda v=value: voteCast(root, frame1, v, client_socket))
        btn.grid(row=row, column=1, pady=5)

        # Load image
        img = ImageTk.PhotoImage(Image.open(img_path).resize((50, 50), Image.LANCZOS))
        lbl = Label(frame1, image=img)
        lbl.image = img  # keep reference!
        lbl.grid(row=row, column=0, padx=5)

    frame1.pack()