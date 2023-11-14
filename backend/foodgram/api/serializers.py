from django.contrib.auth import get_user_model
from djoser.serializers import UserSerializer
from drf_extra_fields.fields import Base64ImageField
from rest_framework.exceptions import ValidationError
from rest_framework.fields import IntegerField, CharField
from rest_framework.relations import PrimaryKeyRelatedField
from rest_framework.serializers import ModelSerializer, SerializerMethodField
from rest_framework.validators import UniqueTogetherValidator

from api.decorators import get_related_queryset
from core.services import pass_ingredients
from recipes.models import Ingredient, Recipe, Tag, Favorite, RecipeIngredient, \
    ShoppingCart
from users.models import Subscription

User = get_user_model()


class UserGetSerializer(UserSerializer):
    is_subscribed = SerializerMethodField(method_name='_is_subscribed')
    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'first_name', 'last_name',
                  'is_subscribed')

    @get_related_queryset('follower', 'author')
    def _is_subscribed(self, obj):
        pass


class IngredientSerializer(ModelSerializer):
    class Meta:
        model = Ingredient
        fields = '__all__'
        read_only_fields = ('__all__',)


class TagSerializer(ModelSerializer):
    class Meta:
        model = Tag
        fields = '__all__'
        read_only_fields = ('__all__',)


class IngredientGetSerializer(ModelSerializer):
    id = IntegerField(read_only=True, source='ingredient.id')
    name = CharField(source='ingredient.name', read_only=True)
    measurement_unit = CharField(source='ingredient.measurement_unit',
                                 read_only=True)

    class Meta:
        model = RecipeIngredient
        fields = ('id', 'name', 'measurement_unit', 'amount')


class IngredientPostSerializer(ModelSerializer):
    id = IntegerField()
    amount = IntegerField()

    class Meta:
        model = RecipeIngredient
        fields = ('id', 'amount')


class RecipeGetSerializer(ModelSerializer):
    image = Base64ImageField(required=True)
    tags = TagSerializer(many=True, read_only=True)
    author = UserGetSerializer()
    is_in_shopping_cart = SerializerMethodField(
        method_name='_is_in_shopping_cart')
    is_favorited = SerializerMethodField(method_name='_is_favorited')
    ingredients = IngredientGetSerializer(many=True, read_only=True,
                                          source='recipeingredients')

    class Meta:
        model = Recipe
        fields = ('id', 'tags', 'author', 'ingredients',
                  'is_favorited', 'is_in_shopping_cart',
                  'name', 'image', 'text', 'cooking_time')

    @get_related_queryset('favorites', 'recipe')
    def _is_favorited(self, obj):
        pass

    @get_related_queryset('shoppingcarts', 'recipe')
    def _is_in_shopping_cart(self, obj):
        pass


class RecipePostSerializer(ModelSerializer):
    ingredients = IngredientPostSerializer(many=True,
                                           source='recipeingredients')
    tags = PrimaryKeyRelatedField(many=True,
                                  queryset=Tag.objects.all())
    image = Base64ImageField(required=True)

    class Meta:
        model = Recipe
        fields = ('ingredients', 'tags', 'image', 'name',
                  'text', 'cooking_time')

    def validate(self, data):
        if not data.get('recipeingredients'):
            raise ValidationError('В рецепте должен быть'
                                  'как минимум один ингредиент.')
        # if len(set(data.get('recipeingredients'))) != len(
        #         data.get('recipeingredients')):
        #     raise ValidationError('Ингредиенты должны быть уникальными.')
        return data

    def create(self, validated_data):
        ingredients = validated_data.pop('recipeingredients')
        tags = validated_data.pop('tags')
        recipe = Recipe.objects.create(author=self.context.get('request').user,
                                       **validated_data)
        recipe.tags.set(tags)
        pass_ingredients(ingredients, recipe)
        return recipe

    def update(self, instance, validated_data):
        ingredients = validated_data.pop('recipeingredients')
        tags = validated_data.pop('tags')
        instance.tags.clear()
        instance.tags.set(tags)
        RecipeIngredient.objects.filter(recipe=instance).delete()
        pass_ingredients(ingredients, instance)
        return super().update(instance, validated_data)

    def to_representation(self, instance):
        return RecipeGetSerializer(instance).data


class FavoriteSerializer(ModelSerializer):
    class Meta:
        model = Favorite
        fields = '__all__'
        validators = [
            UniqueTogetherValidator(
                queryset=Favorite.objects.all(),
                fields=('user', 'recipe'),
                message='Этот рецепт уже добавлен в избранное.'
            )
        ]


class ShoppingCartSerializer(ModelSerializer):
    class Meta:
        model = ShoppingCart
        fields = '__all__'


class RecipeMinifiedSerializer(ModelSerializer):
    class Meta:
        model = Recipe
        fields = ('id', 'name', 'image', 'cooking_time')
        read_only_fields = ('__all__',)


class SubscriptionsListSerializer(ModelSerializer):
    recipes = SerializerMethodField(method_name='_recipes')
    recipes_count = SerializerMethodField(method_name='_recipes_count')
    """Подписки пользователя."""

    class Meta:
        model = User
        fields = (
            'id',
            'email',
            'username',
            'first_name',
            'last_name',
            'recipes',
            'recipes_count',
        )
        read_only_fields = ('__all__',)

    def _recipes_count(self, obj):
        return obj.recipes.count()

    def _recipes(self, obj):
        recipes = obj.recipes.all()
        request = self.context.get('request')
        limit = request.query_params.get('recipes_limit')
        if limit:
            recipes = obj.recipes.all()[:int(limit)]
        return RecipeMinifiedSerializer(recipes, many=True,
                                        context={'request': request}).data


class GetRemoveSubscriptionSerializer(ModelSerializer):
    """Добавление и удаление подписок пользователей."""

    class Meta:
        model = Subscription
        fields = '__all__'

    read_only_fields = ('__all__',)
    validators = [
        UniqueTogetherValidator(
        queryset=Subscription.objects.all(),
        fields=('user', 'author'),
        message='Вы уже подписаны на этого автора.'
    )
    ]

    def to_representation(self, instance):
        request = self.context.get('request')
        return SubscriptionsListSerializer(instance.author,
                                           context={'request': request}).data
