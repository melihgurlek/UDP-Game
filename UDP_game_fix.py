import tkinter as tk
from tkinter import scrolledtext
import socket
import threading
import time
import sys


class UDPGame:
    def __init__(
        self,
        root,
        local_player,
        local_ip="127.0.0.1",
        local_port=5000,
        remote_ip="127.0.0.1",
        remote_port=5001
    ):
        self.root = root
        self.local_player = local_player
        self.local_ip = local_ip
        self.local_port = local_port
        self.remote_ip = remote_ip
        self.remote_port = remote_port
        self.arrow_history = []

        self.players = {
            "A": {"credits": 50, "seq": 0, "ack": 0, "missed": 0},
            "B": {"credits": 50, "seq": 0, "ack": 0, "missed": 0},
        }
        self.current_turn = "A"
        self.max_missed = 3
        self.game_over = False
        self.winner = None

        self.packet_history = []
        self.first_packet_A = True
        self.packet_box_y = {"A": 80, "B": 80}

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((self.local_ip, self.local_port))

        self.setup_gui()
        threading.Thread(target=self.receive_packets, daemon=True).start()

    def setup_gui(self):
        self.root.title(f"TCP SEQ/ACK Game - Player {self.local_player}")
        self.root.geometry("900x600")

        # 1) TOP FRAME (Scoreboard)
        scoreboard_frame = tk.Frame(self.root)
        scoreboard_frame.pack(side="top", fill="x", pady=10)

        self.points_label = tk.Label(
            scoreboard_frame, text=self.get_points_text(), font=("Helvetica", 14)
        )
        self.points_label.pack(side="left", padx=(10, 20))

        self.turn_label = tk.Label(
            scoreboard_frame,
            text=f"It is Player {self.current_turn}'s turn",
            font=("Helvetica", 12)
        )
        self.turn_label.pack(side="left")

        # 2) MAIN FRAME with Canvas (left) & Controls (right)
        main_frame = tk.Frame(self.root)
        main_frame.pack(side="top", fill="both", expand=True)

        # LEFT: The canvas expands
        self.canvas = tk.Canvas(main_frame, bg="white")
        self.canvas.pack(side="left", fill="both",
                         expand=True, padx=(10, 5), pady=10)

        # Display initial instructions on the canvas
        if self.local_player == "A":
            self.canvas.create_text(
                300, 200,
                text="START SEQ/ACK GAME BY SENDING A PACKET!",
                fill="black",
                font=("Helvetica", 14),
                tags="initial_instructions"
            )
        else:
            self.canvas.create_text(
                300, 200,
                text="WAIT FOR A PACKET!",
                fill="black",
                font=("Helvetica", 14),
                tags="initial_instructions"
            )

        # RIGHT: Controls in a frame of fixed width
        controls_frame = tk.Frame(main_frame, width=300)
        controls_frame.pack(side="right", fill="y", padx=(5, 10), pady=10)
        controls_frame.pack_propagate(False)

        # Labels and Entries
        lbl_seq = tk.Label(controls_frame, text="SEQ:", wraplength=80)
        lbl_seq.pack(anchor="w", pady=2)
        self.seq_entry = tk.Entry(controls_frame, width=10)
        self.seq_entry.pack(pady=2, fill="x")

        lbl_ack = tk.Label(controls_frame, text="ACK:", wraplength=80)
        lbl_ack.pack(anchor="w", pady=2)
        self.ack_entry = tk.Entry(controls_frame, width=10)
        self.ack_entry.pack(pady=2, fill="x")

        lbl_dl = tk.Label(controls_frame, text="DL:", wraplength=80)
        lbl_dl.pack(anchor="w", pady=2)
        self.dl_entry = tk.Entry(controls_frame, width=10)
        self.dl_entry.pack(pady=2, fill="x")

        # Send Packet
        self.send_button = tk.Button(
            controls_frame, text="Send Packet", command=self.send_packet, width=15
        )
        self.send_button.pack(pady=(10, 5), fill="x")

        # Restart Game
        self.restart_button = tk.Button(
            controls_frame, text="Restart Game", command=self.restart_game, width=15
        )
        self.restart_button.pack(pady=(5, 10), fill="x")

        # Log box
        self.log_textbox = scrolledtext.ScrolledText(
            controls_frame, height=8, state="disabled", wrap="word"
        )
        self.log_textbox.pack(fill="both", expand=True)

    def get_points_text(self):
        return (
            f"Player A: {self.players['A']['credits']} points | "
            f"Player B: {self.players['B']['credits']} points"
        )

    def log(self, message):
        self.log_textbox.config(state="normal")
        self.log_textbox.insert(tk.END, message + "\n")
        self.log_textbox.config(state="disabled")
        self.log_textbox.yview(tk.END)

    def store_packet_history(self, direction, from_player, seq, ack, dl, valid=False):
        """
        Store the last few packets in a list for display, including validity.
        """
        self.packet_history.append(
            (direction, from_player, seq, ack, dl, valid))

    def validate_packet(self, from_player, seq, ack, dl):
        player = from_player
        opponent = "B" if player == "A" else "A"

        # Special case for the first packet from Player A
        if player == "A" and self.first_packet_A:
            if seq == 0:  # Accept SEQ 0 for the first packet
                self.players[player]["seq"] = dl  # Set next expected SEQ
                self.players[player]["ack"] = 0
                self.first_packet_A = False
                self.log(f"Valid first packet from Player A!")
                return True
            else:
                self.log(f"Invalid first packet from Player A! SEQ should be 0.")
                return False

        expected_seq = self.players[player]["ack"] + dl
        expected_ack = self.players[opponent]["seq"]

        if seq != expected_seq or ack != expected_ack:
            # Invalid packet
            self.players[player]["missed"] += 1
            if not (player == "A" and self.first_packet_A):
                self.players[player]["credits"] -= 10

            self.log(
                f"Invalid packet from Player {player}! "
                f"Expected SEQ={expected_seq}, ACK={expected_ack}. "
                f"Missed {self.players[player]['missed']} times."
            )

            if self.players[player]["missed"] >= self.max_missed:
                self.log("Retransmission required! Resend the last packet.")

            self.check_game_status(player)
            if player == "A" and self.first_packet_A:
                self.first_packet_A = False
            return False
        else:
            # Valid packet
            self.players[player]["seq"] = seq + dl
            self.players[player]["ack"] = seq

            if not (player == "A" and self.first_packet_A):
                self.players[player]["credits"] += 10

            self.players[player]["missed"] = 0
            self.log(f"Valid packet from Player {player}!")

            self.check_game_status(player)
            if player == "A" and self.first_packet_A:
                self.first_packet_A = False
            return True

    def check_game_status(self, player):
        opponent = "B" if player == "A" else "A"
        if self.players[player]["credits"] >= 100:
            self.winner = player
            self.log(
                f"Player {player} reached 100 credits! Player {player} wins!")
            self.end_game()
        elif self.players[player]["credits"] <= 0:
            self.winner = opponent
            self.log(
                f"Player {player} reached 0 credits! Player {opponent} wins!")
            self.end_game()

    def end_game(self):
        self.game_over = True
        self.send_button.config(state="disabled")
        if self.winner is not None:
            if self.local_player == self.winner:
                self.canvas.config(bg="green")
                self.canvas.create_text(
                    300, 200,
                    text="YOU WON!",
                    fill="white",
                    font=("Helvetica", 24),
                    tags="endgame"
                )
            else:
                self.canvas.config(bg="red")
                self.canvas.create_text(
                    300, 200,
                    text="YOU LOST!",
                    fill="white",
                    font=("Helvetica", 24),
                    tags="endgame"
                )

    def update_labels(self):
        self.points_label.config(text=self.get_points_text())
        self.turn_label.config(text=f"It is Player {self.current_turn}'s turn")

    def switch_turn(self):
        if self.game_over:
            return
        self.current_turn = "B" if self.current_turn == "A" else "A"
        self.update_labels()

    def update_canvas(self, from_player, seq, ack, dl, success):
        self.canvas.delete("all")

        # Draw scoreboard
        self.canvas.create_text(
            100, 50,
            text=f"Player A: {self.players['A']['credits']} points",
            fill="blue"
        )
        self.canvas.create_text(
            500, 50,
            text=f"Player B: {self.players['B']['credits']} points",
            fill="red"
        )

        # Draw packet history
        self.draw_packet_history_on_canvas()

        # Calculate arrow coordinates with adjusted endpoints
        arrow_start_x = 150 if from_player == "A" else 425
        arrow_end_x = 425 if from_player == "A" else 150

        arrow_start_y = (
            self.packet_box_y["A"] - 35 + 15
            if from_player == "A"
            else self.packet_box_y["B"] - 35 + 15
        )
        arrow_end_y = (
            self.packet_box_y["B"] + 15
            if from_player == "A"
            else self.packet_box_y["A"] + 15
        )

        # Store arrow data
        self.arrow_history.append({
            'start_x': arrow_start_x,
            'start_y': arrow_start_y,
            'end_x': arrow_end_x,
            'end_y': arrow_end_y,
            'success': success
        })

        # Draw all previous arrows
        for arrow in self.arrow_history[:-1]:  # Exclude current arrow
            color = "green" if arrow['success'] else "red"
            self.canvas.create_line(
                arrow['start_x'], arrow['start_y'],
                arrow['end_x'], arrow['end_y'],
                arrow=tk.LAST, fill=color, width=2
            )

        # Animate current arrow
        color = "green" if success else "red"
        for step in range(20):
            progress = step / 19
            current_x = arrow_start_x + \
                (arrow_end_x - arrow_start_x) * progress
            current_y = arrow_start_y + \
                (arrow_end_y - arrow_start_y) * progress

            self.canvas.delete("current_arrow")
            self.canvas.create_line(
                arrow_start_x, arrow_start_y,
                current_x, current_y,
                arrow=tk.LAST, fill=color, width=2, tags="current_arrow"
            )
            self.canvas.update()
            time.sleep(0.05)

        # Draw final permanent arrow after animation
        self.canvas.create_line(
            arrow_start_x, arrow_start_y,
            arrow_end_x, arrow_end_y,
            arrow=tk.LAST, fill=color, width=2
        )

        # If the game ended, show final screen
        if self.game_over and self.winner is not None:
            self.canvas.delete("all")
            win_color = "green" if self.local_player == self.winner else "red"
            self.canvas.config(bg=win_color)
            self.canvas.create_text(
                300, 200,
                text="YOU WON!" if self.local_player == self.winner else "YOU LOST!",
                fill="white",
                font=("Helvetica", 24),
                tags="endgame"
            )

    def draw_packet_history_on_canvas(self):
        """ Display up to the last 8 packets as small boxes, placed under A or B. """
        self.packet_box_y["A"] = 80
        self.packet_box_y["B"] = 80

        recent_packets = self.packet_history[-8:]
        for (direction, from_player, seq, ack, dl, valid) in recent_packets:
            self.draw_packet_box(from_player, seq, ack, dl, valid)

    def draw_packet_box(self, from_player, seq, ack, dl, valid):
        packet_text = f"SEQ:{seq}, ACK:{ack}, DL:{dl}"

        if from_player == "A":
            x_start = 20
            y_start = self.packet_box_y["A"]
            self.packet_box_y["A"] += 35
        else:
            x_start = 420
            y_start = self.packet_box_y["B"]
            self.packet_box_y["B"] += 35

        box_width = 130
        box_height = 30
        x_end = x_start + box_width
        y_end = y_start + box_height

        # Light green if valid, white if invalid
        fill_color = "lightgreen" if valid else "white"

        self.canvas.create_rectangle(
            x_start, y_start, x_end, y_end,
            fill=fill_color, outline="black"
        )

        self.canvas.create_text(
            x_start + box_width / 2, y_start + box_height / 2,
            text=packet_text,
            anchor="center",
            fill="black",
            font=("Helvetica", 10)
        )

    def send_packet(self):
        self.canvas.delete("initial_instructions")
        if self.game_over:
            self.log("Game is over. No more packets can be sent.")
            return

        if self.local_player != self.current_turn:
            self.log(
                f"Not your turn! It is Player {self.current_turn}'s turn.")
            return

        try:
            seq = int(self.seq_entry.get())
            ack = int(self.ack_entry.get())
            dl = int(self.dl_entry.get())

            packet_str = f"{self.local_player},{seq},{ack},{dl}"
            self.sock.sendto(packet_str.encode(),
                             (self.remote_ip, self.remote_port))

            self.log(
                f"Player {self.local_player}: Sent packet SEQ={seq}, ACK={ack}, DL={dl}")

            # Validate and store with the validity
            valid = self.validate_packet(self.local_player, seq, ack, dl)
            self.store_packet_history(
                "Sent", self.local_player, seq, ack, dl, valid=valid)

            self.update_canvas(self.local_player, seq, ack, dl, success=valid)
            self.switch_turn()

        except ValueError:
            self.log(
                "Invalid input. Please enter numeric values for SEQ, ACK, and DL.")

    def receive_packets(self):
        while True:
            try:
                packet, _ = self.sock.recvfrom(1024)
                data = packet.decode().split(",")
                if len(data) != 4:
                    continue

                from_player, seq_str, ack_str, dl_str = data
                seq, ack, dl = int(seq_str), int(ack_str), int(dl_str)

                self.log(
                    f"Received packet from Player {from_player}: SEQ={seq}, ACK={ack}, DL={dl}")

                # Validate for the remote user
                valid = self.validate_packet(from_player, seq, ack, dl)
                # Store with validity
                self.store_packet_history(
                    "Received", from_player, seq, ack, dl, valid=valid)

                # If it's from the opponent, update state
                if from_player != self.local_player:
                    if self.current_turn != from_player:
                        self.current_turn = from_player
                        self.update_labels()

                    self.update_canvas(
                        from_player, seq, ack, dl, success=valid)
                    self.switch_turn()

            except Exception as e:
                self.log(f"Error receiving packet: {e}")

    def restart_game(self):
        self.players = {
            "A": {"credits": 50, "seq": 0, "ack": 0, "missed": 0},
            "B": {"credits": 50, "seq": 0, "ack": 0, "missed": 0},
        }
        self.current_turn = "A"
        self.game_over = False
        self.winner = None
        self.packet_history.clear()
        self.arrow_history.clear()
        self.first_packet_A = True

        self.send_button.config(state="normal")
        self.update_labels()

        self.canvas.delete("all")
        self.canvas.config(bg="white")

        self.log_textbox.config(state="normal")
        self.log_textbox.delete("1.0", tk.END)
        self.log_textbox.config(state="disabled")

        self.log("Game restarted!")


if __name__ == "__main__":
    root = tk.Tk()

    # Basic command-line argument parsing
    local_player = sys.argv[1] if len(sys.argv) > 1 else "A"
    local_ip = sys.argv[2] if len(sys.argv) > 2 else "127.0.0.1"
    local_port = int(sys.argv[3]) if len(sys.argv) > 3 else 5000
    remote_ip = sys.argv[4] if len(sys.argv) > 4 else "127.0.0.1"
    remote_port = int(sys.argv[5]) if len(sys.argv) > 5 else 5001

    game = UDPGame(
        root,
        local_player=local_player,
        local_ip=local_ip,
        local_port=local_port,
        remote_ip=remote_ip,
        remote_port=remote_port
    )
    root.mainloop()
