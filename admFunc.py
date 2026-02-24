import tkinter as tk
from tkinter import *
from PIL import ImageTk, Image
import os
import dframe as df  # your existing data functions

IMAGE_FOLDER = "img"  # folder where party images are stored

def showVotes(root, frame1):
    result = df.show_result()  # get vote counts as dict: {'bjp':0, 'tvk':1, ...}
    root.title("Votes")

    # Clear previous widgets
    for widget in frame1.winfo_children():
        widget.destroy()

    Label(frame1, text="Vote Count", font=('Helvetica', 18, 'bold')).grid(row=0, column=1, columnspan=2, pady=10)

    row_index = 1
    for party, votes in result.items():
        # Check if image exists for this party
        img_path_jpg = os.path.join(IMAGE_FOLDER, f"{party}.jpg")
        img_path_png = os.path.join(IMAGE_FOLDER, f"{party}.png")
        img = None
        if os.path.exists(img_path_png):
            img = ImageTk.PhotoImage(Image.open(img_path_png).resize((35,35), Image.LANCZOS))
        elif os.path.exists(img_path_jpg):
            img = ImageTk.PhotoImage(Image.open(img_path_jpg).resize((35,35), Image.LANCZOS))

        if img:
            lbl_img = Label(frame1, image=img)
            lbl_img.image = img  # keep reference!
            lbl_img.grid(row=row_index, column=0, padx=5)

        # Display party name and votes
        Label(frame1, text=f"{party.upper()} :", font=('Helvetica', 12, 'bold')).grid(row=row_index, column=1, sticky=W, padx=5)
        Label(frame1, text=str(votes), font=('Helvetica', 12, 'bold')).grid(row=row_index, column=2, sticky=W, padx=5)

        row_index += 1

    frame1.pack()
    root.mainloop()