import os.path
from typing import IO, List, Optional, Any, Callable
from enum import Enum

from .lexing import Lexer, Token, TokenType, CharacterType, STRING_ESCAPE


class SourceMetadata:

    def __init__(self, path: str):
        self.path = path


class Source:

    def __init__(
                self,
                stream: IO,
                metadata: SourceMetadata
            ):
        self.stream = stream
        self.metadata = metadata


class PhpException(Exception):
    pass


class ParsingException(PhpException):
    pass


class EvaluationException(PhpException):
    pass


class PhpState:
    pass


class PhpEntity:

    def __init__(self):
        self.comments = []

    def attach_comment(self, comment: str) -> None:
        self.comments.append(comment)

    def attach_comments(self, comments: List[str]) -> None:
        self.comments.extend(comments)


class PhpType(Enum):
    STRING = str,
    INTEGER = int


class PhpIdentifiedEntity(PhpEntity):

    def __init__(self, name: str):
        super().__init__()
        self.name = name


class Evaluable:

    def evaluate(self, state: PhpState) -> Any:
        return None


class PhpLiteral(PhpEntity, Evaluable):

    def __init__(self, type: PhpType, value: Any):
        if not isinstance(value, type):
            raise ValueError(
                    f'Incompatible type and value: {repr(value)}, type: {type}'
                )
        self.type = type
        self.value = value

    def evaluate(self, state: PhpState) -> Any:
        return self.value


OPERATOR_MAP = dict()


class PhpBinaryOperator(PhpEntity):

    def __init__(
                self,
                operator: str,
                callable: Callable[[Any, Any], Any]
            ):
        super().__init__()
        self.operator = operator
        self.callable = callable

    def apply(self, left: Any, right: Any) -> Any:
        return self.callable(left, right)


def _register_operator(operator: str, callable: Callable[[Any, Any], Any]):
    operator_instance = PhpBinaryOperator(operator, callable)
    OPERATOR_MAP[operator] = operator_instance


_register_operator(
        '.',
        lambda left, right: left + right
    )


class PhpExpression(PhpEntity, Evaluable):

    def __init__(self):
        self.components = []

    def add_component(self, component: PhpEntity) -> None:
        self.components.append(component)

    def evaluate(self, state: PhpState) -> Any:
        operator = None
        value = None
        # print(repr(self.components))
        for component in self.components:
            if isinstance(component, Evaluable):
                new_value = component.evaluate(state)
                if operator is None:
                    if value is not None:
                        raise EvaluationException(
                                'Unexpected adjacent expressions'
                            )
                    value = new_value
                else:
                    value = operator.apply(value, new_value)
            elif isinstance(component, PhpBinaryOperator):
                if operator is not None:
                    raise EvaluationException('Unexpected adjacent operators')
                operator = component
            else:
                raise ParsingException('Not yet implemented')
        return value


class PhpDeclaration(PhpIdentifiedEntity):

    def __init__(self):
        pass


class PhpInstruction(PhpExpression):

    def __init__(self):
        pass


class PhpVariable(PhpIdentifiedEntity):
    pass


class PhpMagicConstant(PhpEntity, Evaluable):

    def __init__(
                self,
                token_type: TokenType,
                source_metadata: SourceMetadata
            ):
        self.token_type = token_type
        self.source_metadata = source_metadata

    def evaluate(self, state: PhpState) -> Any:
        if self.token_type == TokenType.DIR:
            return os.path.dirname(self.source_metadata.path)
        else:
            raise EvaluationException('Unsupported magic constant')


class PhpAssignment(PhpInstruction):

    def __init__(
                self,
                destination: PhpEntity,
                source: PhpExpression
            ):
        self.destination = destination
        self.source = source


class PhpInclude(PhpInstruction):

    def __init__(
                self,
                path: PhpExpression,
                required: bool = False,
                once: bool = False
            ):
        self.path = path
        self.required = required
        self.once = once

    def evaluate_path(self, state: PhpState) -> str:
        path = self.path.evaluate(state)
        if isinstance(path, str):
            return path
        raise EvaluationException(
                'Included path is not a string, received: {repr(path)}'
            )


class PhpContext:

    def __init__(self):
        self.instructions = []
        self.state = PhpState()

    def evaluate_variable(self, name: str) -> Any:
        for instruction in self.instructions:
            if isinstance(instruction, PhpAssignment):
                destination = instruction.destination
                if isinstance(destination, PhpVariable):
                    if destination.name == name:
                        return instruction.source.evaluate(self.state)
        return None

    def get_includes(self) -> List[PhpInclude]:
        includes = []
        for instruction in self.instructions:
            if isinstance(instruction, PhpInclude):
                includes.append(instruction)
        return includes


COMMENT_TOKEN_TYPES = {
        TokenType.DOC_COMMENT
    }
INCLUDE_TOKEN_TYPES = {
        TokenType.INCLUDE,
        TokenType.INCLUDE_ONCE,
        TokenType.REQUIRE,
        TokenType.REQUIRE_ONCE
    }
REQUIRE_TOKEN_TYPES = {
        TokenType.REQUIRE,
        TokenType.REQUIRE_ONCE
    }
INCLUDE_ONCE_TOKEN_TYPES = {
        TokenType.INCLUDE_ONCE,
        TokenType.REQUIRE_ONCE
    }
MAGIC_CONSTANT_TOKEN_TYPES = {
        TokenType.LINE,
        TokenType.FILE,
        TokenType.DIR,
        TokenType.CLASS_C,
        TokenType.TRAIT_C,
        TokenType.METHOD_C,
        TokenType.FUNC_C,
        TokenType.NS_C
    }
BINARY_OPERATORS = {
        '.'
    }


class TokenStream:

    def __init__(self, lexer: Lexer):
        self.lexer = lexer
        self.pending_comments = []

    def accept_token(self) -> Optional[Token]:
        while (token := self.lexer.get_next_token()) is not None:
            if token.type == TokenType.WHITESPACE:
                continue
            if token.type in COMMENT_TOKEN_TYPES:
                self.pending_comments.append(token.value)
            else:
                # print(f"Token({token.type}): {token.value}")
                return token
        return None

    def require_token(self) -> Token:
        token = self.accept_token()
        if token is None:
            raise ParsingException('Token expected')
        return token

    def require_semicolon(self) -> None:
        token = self.require_token()
        if token.is_semicolon():
            return
        raise ParsingException('Expected semicolon')

    def require_equals(self) -> None:
        token = self.require_token()
        if token.type == TokenType.CHARACTER \
                and token.value == CharacterType.EQUALS:
            return
        raise ParsingException('Expected equals sign')

    def take_comments(self) -> List[str]:
        comments = self.pending_comments
        self.pending_comments = []
        return comments


class Parser:

    def __init__(self, source: Source):
        self.source = source
        self.lexer = Lexer(source.stream)
        self.token_stream = TokenStream(self.lexer)

    def parse_instruction(
                self,
                token_stream: TokenStream
            ) -> Optional[PhpInstruction]:
        return None

    def parse_string(self, token: Token) -> PhpLiteral:
        if token.type != TokenType.CONSTANT_ENCAPSED_STRING:
            raise ParsingException('Token is not a valid string')
        value = token.value[1:-1].replace(STRING_ESCAPE, '')
        return PhpLiteral(str, value)

    def parse_integer(self, token: Token) -> PhpLiteral:
        if token.type != TokenType.LNUMBER:
            raise ParsingException('Token is not a valid integer literal')
        value = int(token.value)
        return PhpLiteral(int, value)

    def parse_magic_constant(self, token: Token) -> PhpMagicConstant:
        if token.type not in MAGIC_CONSTANT_TOKEN_TYPES:
            raise ParsingException('Token is not a magic constant')
        return PhpMagicConstant(token.type, self.source.metadata)

    def parse_binary_operator(self, token: Token) -> PhpBinaryOperator:
        try:
            return OPERATOR_MAP[token.value]
        except KeyError:
            raise ParsingException(f'Unrecognized operator: {token.value}')

    def parse_expression_component(self, token: Token) -> PhpEntity:
        if token.type == TokenType.CONSTANT_ENCAPSED_STRING:
            return self.parse_string(token)
        elif token.type == TokenType.LNUMBER:
            return self.parse_integer(token)
        elif token.type in MAGIC_CONSTANT_TOKEN_TYPES:
            return self.parse_magic_constant(token)
        elif token.type == TokenType.CHARACTER \
                and token.value in BINARY_OPERATORS:
            return self.parse_binary_operator(token)
        else:
            raise ParsingException(
                    f'Unrecognized token in expression({token.type.name}):'
                    f' {token.value}'
                )

    def parse_expression(
                self,
                token_stream: TokenStream
            ) -> PhpExpression:
        expression = PhpExpression()
        while True:
            token = token_stream.require_token()
            if token.is_semicolon():
                break
            component = self.parse_expression_component(token)
            expression.add_component(component)
        return expression

    def parse_assignment(
                self,
                token: Token,
                token_stream: TokenStream
            ) -> PhpAssignment:
        variable = PhpVariable(
                name=token.value[1:]
            )
        variable.attach_comments(token_stream.take_comments())
        token_stream.require_equals()
        expression = self.parse_expression(token_stream)
        return PhpAssignment(variable, expression)

    def parse_include(
                self,
                token: Token,
                token_stream: TokenStream,
            ) -> PhpInclude:
        expression = self.parse_expression(token_stream)
        return PhpInclude(
                expression,
                required=token in REQUIRE_TOKEN_TYPES,
                once=token in INCLUDE_ONCE_TOKEN_TYPES
            )

    def parse(self) -> PhpContext:
        context = PhpContext()
        while (token := self.token_stream.accept_token()) is not None:
            # print(f'Token - {token.type.name}: `{token.value}`')
            if token.type == TokenType.VARIABLE:
                assignment = self.parse_assignment(token, self.token_stream)
                context.instructions.append(assignment)
            if token.type in INCLUDE_TOKEN_TYPES:
                include = self.parse_include(token, self.token_stream)
                context.instructions.append(include)
        return context


def parse_php_file(path: str) -> PhpContext:
    try:
        with open(path, 'r') as stream:
            metadata = SourceMetadata(path)
            source = Source(stream, metadata)
            parser = Parser(source)
            return parser.parse()
    except OSError as error:
        raise ParsingException(
                f'Unable to read file at {path}'
            ) from error
