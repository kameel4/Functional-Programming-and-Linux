#include <iostream>

// Проверка на вхождение
int contains(int* arr, int elem) {
    for (int i = 0; i < 4; i++) {
        if (arr[i] == elem) {
            return i;
        }
    }
    return -1;
}

// Добавление в первое свободное место
void put_on_free_place(int* arr, int elem) {
    for (int i = 0; i < 4; i++) {
        if (arr[i] == -1) {
            arr[i] = elem;
            return;
        }
    }
}

// Удаление
void delete_elem(int* arr, int elem) {
    for (int i = 0; i < 4; i++) {
        if (arr[i] == elem) {
            arr[i] = -1;
            return;
        }
    }
}
int main(){
    int arr[4] = {-1, -1, -1, -1};
    int N;
    std::cin >> N;
    for (int i = 0; i < N; i ++){
        int new_elem;
        std::cin >> new_elem;
        if (contains(arr, new_elem) == -1){
            put_on_free_place(arr, new_elem);
        } else {
            delete_elem(arr, new_elem);
        }
    }

    if (arr[0] > arr[1]) std::swap(arr[0], arr[1]);
    if (arr[1] > arr[2]) std::swap(arr[1], arr[2]);
    if (arr[0] > arr[1]) std::swap(arr[0], arr[1]);

    std::cout << arr[0] << " " << arr[1] << " " << arr[2];
    return 0;
}