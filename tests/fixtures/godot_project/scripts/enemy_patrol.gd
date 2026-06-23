extends CharacterBody2D

signal patrol_complete

var speed := 100.0

func _ready():
    $Timer.timeout.connect(_on_timer_timeout)

func _on_timer_timeout():
    pass

func _process(delta):
    var target = $"../../NonExistentNode"
