# mock_database.py

# For this prototype, we use standard YOLOv8 COCO classes as our "shelf items"
# because we don't have a custom trained model yet. We map these generic 
# computer vision classes to our store's specific product inventory.

PRODUCTS = {
    # YOLO Class Name : Product Details
    "bottle": {
        "id": 1,
        "name": "Coca-Cola 500ml",
        "barcode": "1111",
        "price": 2.50
    },
    "apple": {
        "id": 2,
        "name": "Fresh Apple",
        "barcode": "2222",
        "price": 0.80
    },
    "cup": {
        "id": 3,
        "name": "Store Coffee Mug",
        "barcode": "3333",
        "price": 5.99
    },
    "book": {
        "id": 4,
        "name": "Notebook",
        "barcode": "4444",
        "price": 3.50
    },
    "cell phone": {
        "id": 5,
        "name": "Smartphone Case",
        "barcode": "5555",
        "price": 15.00
    },
    "mouse": {
        "id": 6,
        "name": "Wireless Mouse",
        "barcode": "6666",
        "price": 25.00
    },
    "scissors": {
        "id": 7,
        "name": "Crafting Scissors",
        "barcode": "7777",
        "price": 4.25
    },
    "toothbrush": {
        "id": 8,
        "name": "Oral-B Toothbrush",
        "barcode": "8888",
        "price": 2.99
    },
    "orange": {
        "id": 9,
        "name": "Fresh Orange",
        "barcode": "9999",
        "price": 0.75
    },
    "banana": {
        "id": 10,
        "name": "Chiquita Banana",
        "barcode": "0000",
        "price": 0.50
    }
}

# Helper to look up a product by its barcode (Simulating the Mobile App scan)
def get_product_by_barcode(barcode):
    for cv_class, details in PRODUCTS.items():
        if details["barcode"] == barcode:
            return cv_class, details
    return None, None
