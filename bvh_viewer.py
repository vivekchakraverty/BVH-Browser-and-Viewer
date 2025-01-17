import sys
import os
import numpy as np
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
    QHBoxLayout, QPushButton, QFileDialog, QSlider, QLabel)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from OpenGL.GL import *
from OpenGL.GLU import *

# [Previous Joint and BVHParser classes remain unchanged]
class Joint:
    def __init__(self, name, offset):
        self.name = name
        self.offset = np.array(offset, dtype=float)
        self.children = []
        self.channels = []

class BVHParser:
    def __init__(self, filename):
        self.joints = {}
        self.root = None
        self.frames = []
        self.frame_time = 0
        self.parse_file(filename)

    def parse_file(self, filename):
        current_joint = None
        joint_stack = []
        
        with open(filename, 'r') as f:
            lines = [line.strip() for line in f.readlines()]
        
        i = 0
        while i < len(lines):
            if 'JOINT' in lines[i] or 'End' in lines[i] or 'ROOT' in lines[i]:
                parts = lines[i].split()
                name = parts[1] if len(parts) > 1 else 'End'
                
                i += 2  # Skip {
                offset = [float(x) for x in lines[i].split()[1:]]
                joint = Joint(name, offset)
                
                if 'ROOT' in lines[i-2]:
                    self.root = joint
                else:
                    joint_stack[-1].children.append(joint)
                    
                joint_stack.append(joint)
                self.joints[name] = joint
                
            elif 'CHANNELS' in lines[i]:
                parts = lines[i].split()
                joint_stack[-1].channels = parts[2:]
                
            elif '}' in lines[i]:
                if joint_stack:
                    joint_stack.pop()
                    
            elif 'MOTION' in lines[i]:
                i += 1
                num_frames = int(lines[i].split()[1])
                i += 1
                self.frame_time = float(lines[i].split()[2])
                
                for f in range(num_frames):
                    i += 1
                    self.frames.append([float(x) for x in lines[i].split()])
            i += 1

class GLWidget(QOpenGLWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.rotation = [0, 0, 0]
        self.scale = 1.0
        self.zoom = -30.0
        self.current_frame = 0
        self.animation_data = None
        self.last_pos = None
        self.mouse_button = None
        
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_frame)
        self.timer.start(33)

    def mousePressEvent(self, event):
        self.last_pos = event.pos()
        self.mouse_button = event.button()

    def mouseMoveEvent(self, event):
        if self.last_pos and self.mouse_button:
            dx = event.x() - self.last_pos.x()
            dy = event.y() - self.last_pos.y()
            
            if self.mouse_button == Qt.MiddleButton:
                self.rotation[1] += dx * 0.5
                self.rotation[0] += dy * 0.5
            elif self.mouse_button == Qt.LeftButton:
                pass
                
            self.last_pos = event.pos()
            self.update()

    def mouseReleaseEvent(self, event):
        self.mouse_button = None
        self.last_pos = None

    def update_frame(self):
        if self.animation_data and self.animation_data.frames:
            self.current_frame = (self.current_frame + 1) % len(self.animation_data.frames)
            self.update()

    def initializeGL(self):
        glEnable(GL_DEPTH_TEST)
        glClearColor(0.2, 0.2, 0.2, 1.0)

    def resizeGL(self, w, h):
        glViewport(0, 0, w, h)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        gluPerspective(45, w/h, 0.1, 100.0)

    def draw_joint(self, joint, frame_data, channel_index=0):
        glPushMatrix()
        glTranslatef(*joint.offset)
        
        glPointSize(max(0.1, abs(5.0 * self.scale)))
        glColor3f(1.0, 0.5, 0.0)
        glBegin(GL_POINTS)
        glVertex3f(0, 0, 0)
        glEnd()
        
        if joint.children:
            glColor3f(1.0, 1.0, 1.0)
            glBegin(GL_LINES)
            for child in joint.children:
                glVertex3f(0, 0, 0)
                if self.scale < 0:
                    glVertex3f(*(-child.offset))
                else:
                    glVertex3f(*child.offset)
            glEnd()
        
        for channel in joint.channels:
            if channel_index >= len(frame_data):
                break
            value = frame_data[channel_index]
            channel_index += 1
            
            if 'rotation' in channel:
                axis = {'X': (1,0,0), 'Y': (0,1,0), 'Z': (0,0,1)}[channel[0]]
                glRotatef(value, *axis)
            elif 'position' in channel:
                pos = [0,0,0]
                pos['XYZ'.index(channel[0])] = value * (abs(self.scale) / self.scale if self.scale != 0 else 1)
                glTranslatef(*pos)
        
        for child in joint.children:
            channel_index = self.draw_joint(child, frame_data, channel_index)
        
        glPopMatrix()
        return channel_index

    def paintGL(self):
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        
        glTranslatef(0, -5, self.zoom)
        glRotatef(self.rotation[0], 1, 0, 0)
        glRotatef(self.rotation[1], 0, 1, 0)
        
        glScalef(abs(self.scale), abs(self.scale), abs(self.scale))
        
        if self.animation_data and self.animation_data.root:
            if self.current_frame < len(self.animation_data.frames):
                self.draw_joint(self.animation_data.root, 
                              self.animation_data.frames[self.current_frame])

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("BVH Viewer")
        self.current_file_index = 0
        self.bvh_files = []
        self.current_filename = ""

        main_widget = QWidget()
        layout = QVBoxLayout()
        
        # Add filename label at the top
        self.filename_label = QLabel("No file loaded")
        self.filename_label.setAlignment(Qt.AlignCenter)
        self.filename_label.setStyleSheet("font-weight: bold; padding: 5px;")
        layout.addWidget(self.filename_label)
        
        self.gl_widget = GLWidget()
        layout.addWidget(self.gl_widget)
        
        controls = QVBoxLayout()
        self.load_btn = QPushButton("Load Directory")
        self.prev_btn = QPushButton("Previous")
        self.next_btn = QPushButton("Next")
        
        scale_layout = QHBoxLayout()
        scale_layout.addWidget(QLabel("Scale:"))
        self.scale_slider = QSlider(Qt.Horizontal)
        self.scale_slider.setRange(-200, 400)
        self.scale_slider.setValue(100)
        self.scale_value_label = QLabel("1.0")
        scale_layout.addWidget(self.scale_slider)
        scale_layout.addWidget(self.scale_value_label)
        
        zoom_layout = QHBoxLayout()
        zoom_layout.addWidget(QLabel("Zoom:"))
        self.zoom_slider = QSlider(Qt.Horizontal)
        self.zoom_slider.setRange(-100, -5)
        self.zoom_slider.setValue(-30)
        zoom_layout.addWidget(self.zoom_slider)
        
        self.load_btn.clicked.connect(self.load_directory)
        self.prev_btn.clicked.connect(self.prev_animation)
        self.next_btn.clicked.connect(self.next_animation)
        self.scale_slider.valueChanged.connect(self.update_scale)
        self.zoom_slider.valueChanged.connect(self.update_zoom)
        
        for widget in (self.load_btn, self.prev_btn, self.next_btn):
            controls.addWidget(widget)
        controls.addLayout(scale_layout)
        controls.addLayout(zoom_layout)
            
        layout.addLayout(controls)
        main_widget.setLayout(layout)
        self.setCentralWidget(main_widget)

    def update_zoom(self, value):
        self.gl_widget.zoom = float(value)
        self.gl_widget.update()

    def update_scale(self, value):
        scale = value / 100.0
        self.gl_widget.scale = scale
        self.scale_value_label.setText(f"{scale:.2f}")
        self.gl_widget.update()

    def update_filename_label(self, filename):
        if filename:
            basename = os.path.basename(filename)
            self.filename_label.setText(f"Current Animation: {basename}")
        else:
            self.filename_label.setText("No file loaded")

    def load_directory(self):
        directory = QFileDialog.getExistingDirectory(self)
        if directory:
            self.bvh_files = [os.path.join(directory, f) for f in os.listdir(directory) 
                             if f.lower().endswith('.bvh')]
            if self.bvh_files:
                self.load_animation(self.bvh_files[0])

    def load_animation(self, filename):
        try:
            self.gl_widget.animation_data = BVHParser(filename)
            self.gl_widget.current_frame = 0
            self.update_filename_label(filename)
        except Exception as e:
            print(f"Error loading {filename}: {e}")
            self.update_filename_label(None)

    def next_animation(self):
        if self.bvh_files:
            self.current_file_index = (self.current_file_index + 1) % len(self.bvh_files)
            self.load_animation(self.bvh_files[self.current_file_index])

    def prev_animation(self):
        if self.bvh_files:
            self.current_file_index = (self.current_file_index - 1) % len(self.bvh_files)
            self.load_animation(self.bvh_files[self.current_file_index])

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.resize(800, 600)
    window.show()
    sys.exit(app.exec())
